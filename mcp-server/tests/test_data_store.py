import pytest

from src import data_store as ds


# ---- NIST -----------------------------------------------------------------
class TestNist:
    def test_lookup_known(self):
        c = ds.nist_control_lookup("AC-2")
        assert c is not None
        assert c.id == "AC-2"
        assert c.family == "Access Control"
        assert "AC-3" in c.related
        assert c.cmmc_l2_practices

    def test_lookup_case_insensitive(self):
        assert ds.nist_control_lookup("ac-2").id == "AC-2"

    def test_lookup_unknown(self):
        assert ds.nist_control_lookup("ZZ-99") is None

    def test_available_has_ten(self):
        assert len(ds.nist_available_controls()) == 10


# ---- POA&Ms ---------------------------------------------------------------
class TestPoams:
    def test_list_all(self, poam_db):
        items = ds.poam_list(db_path=poam_db)
        assert len(items) == 5

    def test_list_filtered(self, poam_db):
        opens = ds.poam_list(status_filter="open", db_path=poam_db)
        assert opens and all(p.status == "open" for p in opens)

    def test_invalid_status_rejected(self, poam_db):
        with pytest.raises(ValueError):
            ds.poam_list(status_filter="'; DROP TABLE poams; --", db_path=poam_db)

    def test_severity_ordering(self, poam_db):
        items = ds.poam_list(db_path=poam_db)
        order = {"critical": 0, "high": 1, "moderate": 2, "low": 3}
        sev = [order[p.severity] for p in items]
        assert sev == sorted(sev)

    def test_milestones_parsed(self, poam_db):
        items = ds.poam_list(db_path=poam_db)
        assert any(isinstance(p.milestones, list) and p.milestones for p in items)

    def test_summary(self, poam_db):
        s = ds.poam_summary(db_path=poam_db)
        assert s.total == 5
        assert sum(s.by_severity.values()) == 5
        assert sum(s.by_status.values()) == 5

    def test_readonly_cannot_write(self, poam_db):
        import sqlite3
        conn = ds._connect_ro(poam_db)
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("DELETE FROM poams")
        conn.close()


# ---- CMMC -----------------------------------------------------------------
class TestCmmc:
    def test_totals_consistent(self):
        s = ds.cmmc_level2_status()
        assert s.total_practices == 110
        assert s.implemented + s.partial + s.not_implemented == 110

    def test_domains_sum_to_total(self):
        s = ds.cmmc_level2_status()
        assert sum(d.total for d in s.domains) == 110
        for d in s.domains:
            assert d.implemented + d.partial + d.not_implemented == d.total

    def test_has_disclaimer(self):
        assert "reference design" in ds.cmmc_level2_status().disclaimer.lower()

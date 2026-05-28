from src import sam_client as sc


def _entity(payload):
    return sc.parse_entity(payload)


class TestParse:
    def test_core_fields(self, sam_payload):
        e = _entity(sam_payload)
        assert e.uei == "ZQGGHJH74DW7"
        assert e.cage_code == "14HQ0"
        assert e.legal_business_name == "OPTIMAL, LLC"
        assert e.registration_status == "Active"

    def test_business_types(self, sam_payload):
        e = _entity(sam_payload)
        assert "Veteran Owned Business" in e.business_types

    def test_naics_with_primary_flag(self, sam_payload):
        e = _entity(sam_payload)
        codes = {n.code: n.primary for n in e.naics}
        assert codes["541512"] is True
        assert codes["541519"] is False

    def test_poc_parsed(self, sam_payload):
        e = _entity(sam_payload)
        assert e.points_of_contact[0].email == "poc@example.com"

    def test_empty_payload(self):
        assert sc.parse_entity({"entityData": []}) is None


class TestRedaction:
    def test_non_admin_redacted(self, sam_payload):
        e = sc.redact_entity(_entity(sam_payload), include_pii=True, is_admin=False)
        assert e.points_of_contact[0].email == "[REDACTED]"
        assert e.points_of_contact[0].phone == "[REDACTED]"
        assert e.pii_included is False

    def test_admin_without_flag_redacted(self, sam_payload):
        e = sc.redact_entity(_entity(sam_payload), include_pii=False, is_admin=True)
        assert e.points_of_contact[0].email == "[REDACTED]"
        assert e.pii_included is False

    def test_admin_with_flag_unmasked(self, sam_payload):
        e = sc.redact_entity(_entity(sam_payload), include_pii=True, is_admin=True)
        assert e.points_of_contact[0].email == "poc@example.com"
        assert e.points_of_contact[0].phone == "8135551234"
        assert e.pii_included is True

    def test_name_never_redacted(self, sam_payload):
        e = sc.redact_entity(_entity(sam_payload), include_pii=False, is_admin=False)
        assert e.points_of_contact[0].name  # name is not PII-gated


class TestClassify:
    def test_uei(self):
        assert sc.classify_identifier("ZQGGHJH74DW7") == "uei"

    def test_cage(self):
        assert sc.classify_identifier("14HQ0") == "cage"

    def test_invalid(self):
        import pytest
        with pytest.raises(ValueError):
            sc.classify_identifier("nope")

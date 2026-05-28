import os
import sqlite3
import sys

import pytest

# make `src` importable as a package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

SEED = os.path.join(os.path.dirname(__file__), "..", "data", "seed_poams.sql")


@pytest.fixture()
def poam_db(tmp_path):
    """A fresh read-only-able POA&M db built from the shipped seed SQL."""
    db = tmp_path / "poams.db"
    conn = sqlite3.connect(str(db))
    with open(SEED) as fh:
        conn.executescript(fh.read())
    conn.commit()
    conn.close()
    return str(db)


@pytest.fixture()
def sam_payload():
    """Representative SAM.gov v3 payload shape (documented field names)."""
    return {
        "entityData": [{
            "entityRegistration": {
                "ueiSAM": "ZQGGHJH74DW7",
                "cageCode": "14HQ0",
                "legalBusinessName": "OPTIMAL, LLC",
                "registrationStatus": "Active",
                "registrationDate": "2023-01-15",
                "registrationExpirationDate": "2026-01-14",
            },
            "coreData": {
                "businessTypes": {
                    "businessTypeList": [
                        {"businessTypeCode": "2X", "businessTypeDesc": "Veteran Owned Business"},
                        {"businessTypeCode": "QF", "businessTypeDesc": "Service-Disabled Veteran Owned"},
                    ]
                }
            },
            "assertions": {
                "goodsAndServices": {
                    "primaryNaics": "541512",
                    "naicsList": [
                        {"naicsCode": "541512", "naicsDescription": "Computer Systems Design Services"},
                        {"naicsCode": "541519", "naicsDescription": "Other Computer Related Services"},
                    ],
                }
            },
            "pointsOfContact": {
                "governmentBusinessPOC": {
                    "firstName": "Ryan", "lastName": "G", "title": "Owner",
                    "email": "poc@example.com", "usPhone": "8135551234",
                },
            },
        }]
    }

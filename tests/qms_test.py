import json
import unittest

from scripts.check_qms import ROOT, validate_register, validate_soup


class QmsTest(unittest.TestCase):
    def setUp(self):
        self.register = json.loads(
            (ROOT / "docs/qms/register.json").read_text(encoding="utf-8")
        )

    def test_current_register_and_inventory(self):
        self.assertEqual(validate_register(ROOT, self.register), [])
        self.assertEqual(validate_soup(ROOT), [])

    def test_missing_hazard_and_test_are_rejected(self):
        item = self.register["requirements"][0]
        item["hazards"] = ["H-999"]
        item["evidence"] = ["backend/tests/test_identity.py::test_missing"]
        issues = validate_register(ROOT, self.register)
        self.assertTrue(any("unknown hazard link" in issue for issue in issues))
        self.assertTrue(any("unresolved test" in issue for issue in issues))

    def test_clinical_release_refuses_unresolved_hazards(self):
        issues = validate_register(ROOT, self.register, release=True)
        self.assertIn("H-06: blocks clinical release", issues)

    def test_acceptance_requires_references(self):
        self.register["hazards"][0]["status"] = "accepted"
        self.assertIn(
            "H-01: accepted risk lacks approval or verification reference",
            validate_register(ROOT, self.register, release=True),
        )

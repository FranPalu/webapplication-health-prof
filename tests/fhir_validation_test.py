import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "check_fhir_validation",
    Path(__file__).resolve().parents[1] / "scripts/check_fhir_validation.py",
)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ValidationGateTests(unittest.TestCase):
    def test_warning_report_is_not_promoted_to_clinical_conformance(self):
        self.assertEqual(
            module.check_result(
                {"resourceType": "OperationOutcome", "issue": [{"severity": "warning"}]}
            ),
            {"warning": 1},
        )

    def test_errors_fail_even_if_java_process_exits_successfully(self):
        for report in (
            {},
            {"resourceType": "Bundle", "entry": []},
            {"resourceType": "OperationOutcome", "issue": [{"severity": "error"}]},
            {"resourceType": "OperationOutcome", "issue": [{"severity": "fatal"}]},
            {"resourceType": "OperationOutcome", "issue": [{"severity": "unexpected"}]},
        ):
            with self.subTest(report=report), self.assertRaises(ValueError):
                module.check_result(report)

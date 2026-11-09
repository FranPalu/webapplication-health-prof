"""Synthetic negative cases for the disconnected imaging smoke runner."""

import hashlib
import tempfile
import unittest
from pathlib import Path

from contract import validate_fixture


class ImagingContractTests(unittest.TestCase):
    def test_supported_synthetic_fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = b"synthetic fixture bytes"
            ((root / "synthetic.png").resolve()).write_bytes(data)
            manifest = {
                "source": "synthetic",
                "modality": "chest_xray",
                "view": "PA",
                "file": "synthetic.png",
                "sha256": hashlib.sha256(data).hexdigest(),
            }
            self.assertEqual(
                validate_fixture(root, manifest), (root / "synthetic.png").resolve()
            )
            for changes in (
                {"modality": "CT"},
                {"view": "lateral"},
                {"source": "patient"},
                {"sha256": "0" * 64},
                {"file": "../escape.png"},
            ):
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    validate_fixture(root, {**manifest, **changes})


if __name__ == "__main__":
    unittest.main()

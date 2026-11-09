"""The quarantined converter must reject any unpinned legacy input before loading."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import convert_legacy


class ConversionSafetyTests(unittest.TestCase):
    def test_tampered_checkpoint_is_never_deserialized(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "untrusted.pt"
            source.write_bytes(b"SYNTHETIC UNTRUSTED CHECKPOINT")
            with (
                patch.object(convert_legacy, "Path", return_value=source),
                patch.object(convert_legacy.torch, "load") as loader,
            ):
                with self.assertRaisesRegex(ValueError, "Untrusted legacy checkpoint"):
                    convert_legacy.main()
                loader.assert_not_called()


if __name__ == "__main__":
    unittest.main()

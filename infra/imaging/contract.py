"""Technical fixture contract. Metadata checks are not a clinical OOD detector."""

import hashlib


def validate_fixture(root, manifest):
    if manifest.get("source") not in ("synthetic", "authorized_public"):
        raise ValueError("Unapproved fixture source")
    if (
        manifest.get("view") not in ("AP", "PA")
        or manifest.get("modality") != "chest_xray"
    ):
        raise ValueError("Only frontal chest radiographs are supported")
    path = (root / manifest["file"]).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("Invalid fixture path")
    if not 0 < path.stat().st_size <= 10 * 1024 * 1024:
        raise ValueError("Invalid fixture size")
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["sha256"]:
        raise ValueError("Fixture checksum mismatch")
    return path

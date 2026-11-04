"""Offline smoke runner for a pinned upstream TorchXRayVision checkpoint."""

import hashlib
import json
from pathlib import Path

import numpy as np
import torch
import torchxrayvision as xrv
from PIL import Image

CHECKSUM = "56524913dd16a906422e8d8b66a7a5c46be1d82eb7ac012d8103776f1aa68899"
ROOT = Path("/fixtures")


def fixture():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    if manifest["source"] not in ("synthetic", "authorized_public"):
        raise ValueError("Unapproved fixture source")
    if manifest["view"] not in ("AP", "PA") or manifest["modality"] != "chest_xray":
        raise ValueError("Only frontal chest radiographs are supported")
    path = (ROOT / manifest["file"]).resolve()
    if not path.is_relative_to(ROOT) or path.stat().st_size > 10 * 1024 * 1024:
        raise ValueError("Invalid fixture path or size")
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["sha256"]:
        raise ValueError("Fixture checksum mismatch")
    with Image.open(path, formats=["PNG", "JPEG"]) as image:
        if image.width * image.height > 16_000_000:
            raise ValueError("Fixture dimensions exceeded")
        return np.asarray(image.convert("L"))


def main():
    pixels = fixture()
    weights = Path("/models/xray.pt")
    with weights.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != CHECKSUM:
            raise ValueError("Checkpoint checksum mismatch")
    # The pinned upstream artifact is a full pickled model. Load only this
    # artifact inside the read-only, disconnected test container.
    model = torch.load(weights, map_location="cpu", weights_only=False).eval()
    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    image = xrv.datasets.normalize(pixels, 255)[None, :, :]
    image = xrv.datasets.XRayResizer(224)(xrv.datasets.XRayCenterCrop()(image))
    with torch.inference_mode():
        tensor = torch.from_numpy(image).unsqueeze(0)
        result = model(tensor)
        repeated = model(tensor)
    if not torch.isfinite(result).all() or not torch.equal(result, repeated):
        raise ValueError("Invalid or nonreproducible model output")
    print(
        json.dumps(
            {
                "model": "densenet121-res224-all",
                "sha256": CHECKSUM,
                "scope": "research smoke test only",
                "scores": result.tolist(),
                "repeatable": True,
            }
        )
    )


if __name__ == "__main__":
    main()

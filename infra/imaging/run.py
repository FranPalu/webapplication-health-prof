"""Offline smoke runner for a pinned upstream TorchXRayVision checkpoint."""

import hashlib
import json
from pathlib import Path

import numpy as np
import torch
import torchxrayvision as xrv
from contract import validate_fixture
from PIL import Image

CHECKSUM = "9557a4685000af1490869d2abb19be6a651beb57feff6c1da8cf88bef28eb068"
ROOT = Path("/fixtures")


def fixture():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    path = validate_fixture(ROOT, manifest)
    with Image.open(path, formats=["PNG", "JPEG"]) as image:
        if image.width * image.height > 16_000_000:
            raise ValueError("Fixture dimensions exceeded")
        return np.asarray(image.convert("L"))


def main():
    pixels = fixture()
    weights = Path("/models/converted/xray-state.pt")
    with weights.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != CHECKSUM:
            raise ValueError("Checkpoint checksum mismatch")
    # Only tensor state is accepted during inference; never load a model object.
    state = torch.load(weights, map_location="cpu", weights_only=True)
    model = xrv.models.DenseNet(weights=None).eval()
    model.load_state_dict(state, strict=True)
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
                "clinical_usable": False,
                "confidence": None,
                "calibration": "not clinically validated",
                "localization": None,
                "ood_detection": "metadata contract only; no clinical OOD validation",
            }
        )
    )


if __name__ == "__main__":
    main()

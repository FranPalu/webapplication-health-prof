"""One-time quarantined conversion of exactly one pinned upstream artifact.

Run only through the disconnected imaging-convert Compose profile. This tool
is not part of the inference entrypoint and must never accept patient inputs.
"""

import hashlib
from pathlib import Path

import torch
import torchxrayvision as xrv

LEGACY_SHA256 = "56524913dd16a906422e8d8b66a7a5c46be1d82eb7ac012d8103776f1aa68899"


def main():
    source = Path("/legacy/xray.pt")
    with source.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != LEGACY_SHA256:
            raise ValueError("Untrusted legacy checkpoint")
    # B614 disposition: one exact upstream hash, offline read-only quarantine,
    # no patient input, no DB, no credentials. Legacy format cannot be read by
    # weights_only=True. The inference runner never executes this loader.
    original = torch.load(source, map_location="cpu", weights_only=False).eval()  # nosec B614
    if type(original) is not xrv.models.DenseNet:
        raise ValueError("Unexpected architecture")
    if (
        getattr(original, "apply_sigmoid", False)
        or getattr(original, "op_threshs", None) is not None
    ):
        raise ValueError("Unsupported postprocessing")
    state = original.state_dict()
    if not all(isinstance(value, torch.Tensor) for value in state.values()):
        raise ValueError("Non-tensor state")
    safe = xrv.models.DenseNet(weights=None).eval()
    safe.load_state_dict(state, strict=True)
    torch.set_num_threads(2)
    fixture = torch.zeros((1, 1, 224, 224))
    with torch.inference_mode():
        if not torch.equal(original(fixture), safe(fixture)):
            raise ValueError("Conversion changed inference")
    target = Path("/converted/xray-state.pt")
    torch.save(state, target)
    with target.open("rb") as stream:
        print("converted_sha256", hashlib.file_digest(stream, "sha256").hexdigest())


if __name__ == "__main__":
    main()

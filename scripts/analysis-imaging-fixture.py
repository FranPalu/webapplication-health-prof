"""Generate a deterministic synthetic image for the disconnected imaging smoke test."""

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw

root = Path(".analysis-fixtures")
root.mkdir(exist_ok=True)
image = Image.new("L", (256, 256), 25)
draw = ImageDraw.Draw(image)
draw.ellipse((36, 28, 125, 221), fill=145)
draw.ellipse((131, 28, 220, 221), fill=145)
draw.rectangle((123, 20, 132, 230), fill=195)
file = root / "synthetic-chest.png"
image.save(file)
(root / "manifest.json").write_text(json.dumps({
    "file": file.name, "source": "synthetic", "view": "PA", "modality": "chest_xray",
    "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
}))

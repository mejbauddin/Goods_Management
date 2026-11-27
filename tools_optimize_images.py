"""One-off asset optimisation: convert raw AI renders to progressive JPEG."""
from pathlib import Path

from PIL import Image

IMG = Path(__file__).resolve().parent / "static" / "img"

JOBS = {
    "hero-warehouse.raw": ("hero-warehouse.jpg", 1600),
    "flow-network.raw": ("flow-network.jpg", 1600),
    "cat-electronics.raw": ("cat-electronics.jpg", 640),
    "cat-office.raw": ("cat-office.jpg", 640),
    "cat-packaging.raw": ("cat-packaging.jpg", 640),
    "cat-household.raw": ("cat-household.jpg", 640),
    "empty-box.raw": ("empty-box.jpg", 560),
}

for src, (dst, width) in JOBS.items():
    path = IMG / src
    if not path.exists():
        print(f"skip {src} (missing)")
        continue
    with Image.open(path) as im:
        print(src, im.format, im.size)
        frame = im.convert("RGB")
        if frame.width > width:
            height = int(frame.height * width / frame.width)
            frame = frame.resize((width, height), Image.LANCZOS)
        frame.save(IMG / dst, "JPEG", quality=86, optimize=True, progressive=True)
    path.unlink()

for item in sorted(IMG.iterdir()):
    print(item.name, item.stat().st_size)

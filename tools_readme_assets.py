"""Prepare GitHub README assets: banner + screenshots as compact progressive JPEG."""
from pathlib import Path

from PIL import Image

DOCS = Path(__file__).parent / "docs"
SHOTS = DOCS / "screenshots"


def save(source: Path, target: Path, max_width: int, quality: int) -> None:
    image = Image.open(source).convert("RGB")
    if image.width > max_width:
        height = round(image.height * max_width / image.width)
        image = image.resize((max_width, height), Image.LANCZOS)
    image.save(target, "JPEG", quality=quality, optimize=True, progressive=True)
    print(f"{target.name:24} {image.width}x{image.height}  {target.stat().st_size // 1024} KB")


save(DOCS / "banner-raw.jpg", DOCS / "banner.jpg", 2400, 84)

for png in sorted(SHOTS.glob("*.png")):
    save(png, png.with_suffix(".jpg"), 1440, 80)
    png.unlink()

(DOCS / "banner-raw.jpg").unlink()
print("done")

"""Goods photo files on disk.

Improvements over the original version:
  * Files are written atomically (temporary file, then rename), so a crash
    or a full disk can never leave a half-written photo behind.
  * A small thumbnail is saved next to every photo (PHOTO_DIR/thumbs) so
    list pages load quickly. Pass thumbnail=False to skip it.
  * Settings (sizes, quality, allowed formats) are named constants.
  * New delete_goods_photo() removes a photo and its thumbnail safely
    (the filename is checked first, so it can never point outside the
    photo folder).
  * New find_unused_photos() / delete_unused_photos() clean up files that
    no goods record uses. Files newer than `min_age_seconds` are never
    touched, so a photo that was just uploaded cannot be deleted before it
    is saved to the database.
  * Saved JPEGs are progressive and optimised, and carry no EXIF data
    (location, camera details), which is good for privacy.

save_goods_photo(upload) still returns the new filename and raises
ValueError with the same messages, so existing code keeps working.
"""

import io
import os
import re
import time
import uuid
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

from database import DATA_DIR


PHOTO_DIR = DATA_DIR / "goods_photos"
THUMB_DIR = PHOTO_DIR / "thumbs"

MAX_PHOTO_BYTES = 5 * 1024 * 1024
MAX_PHOTO_PIXELS = 20_000_000

PHOTO_SIZE = (1200, 1200)
THUMB_SIZE = (320, 320)
PHOTO_QUALITY = 85
THUMB_QUALITY = 80

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}

# The only filenames this module creates (and app.py will serve).
FILENAME_PATTERN = re.compile(r"[0-9a-f]{32}\.jpg")


def is_valid_photo_filename(filename):
    return isinstance(filename, str) and bool(
        FILENAME_PATTERN.fullmatch(filename)
    )


def _decode_image(data):
    """Check the uploaded bytes and return a clean RGB image."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)

            with Image.open(io.BytesIO(data)) as source:
                if source.format not in ALLOWED_FORMATS:
                    raise ValueError(
                        "Please upload a JPG, PNG, or WebP image.")

                if source.width * source.height > MAX_PHOTO_PIXELS:
                    raise ValueError(
                        "The photo is too large. Use a smaller image.")

                source.load()
                oriented = ImageOps.exif_transpose(source)
                rgba = oriented.convert("RGBA")
                rgba.thumbnail(PHOTO_SIZE)

                # Give transparent images a white background.
                image = Image.new("RGB", rgba.size, "white")
                image.paste(rgba, mask=rgba.getchannel("A"))

                return image

    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as error:
        raise ValueError(
            "This file is not a valid supported image.") from error


def _save_jpeg(image, path, quality):
    """Write a JPEG atomically: temp file first, then rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + ".tmp")

    try:
        image.save(
            temp_path,
            format="JPEG",
            quality=quality,
            optimize=True,
            progressive=True,
        )
        os.replace(temp_path, path)

    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def save_goods_photo(upload, *, thumbnail=True):
    """Validate an uploaded image and save a resized JPEG.

    Returns the new filename. Also saves a thumbnail with the same name
    in THUMB_DIR unless thumbnail=False.
    """
    if upload is None or not upload.filename:
        raise ValueError("Please select a photo.")

    data = upload.stream.read(MAX_PHOTO_BYTES + 1)

    if len(data) > MAX_PHOTO_BYTES:
        raise ValueError("The photo must be smaller than 5 MB.")

    if not data:
        raise ValueError("The selected file is empty.")

    image = _decode_image(data)

    filename = f"{uuid.uuid4().hex}.jpg"

    try:
        _save_jpeg(image, PHOTO_DIR / filename, PHOTO_QUALITY)

        if thumbnail:
            small = image.copy()
            small.thumbnail(THUMB_SIZE)
            _save_jpeg(small, THUMB_DIR / filename, THUMB_QUALITY)

    except Exception:
        (PHOTO_DIR / filename).unlink(missing_ok=True)
        (THUMB_DIR / filename).unlink(missing_ok=True)
        raise

    return filename


def delete_goods_photo(filename):
    """Delete a photo and its thumbnail. Returns True if the photo existed.

    Invalid filenames are ignored (returns False) so this can never touch
    files outside the photo folder.
    """
    if not is_valid_photo_filename(filename):
        return False

    (THUMB_DIR / filename).unlink(missing_ok=True)

    path = PHOTO_DIR / filename
    existed = path.exists()
    path.unlink(missing_ok=True)

    return existed


def find_unused_photos(used_filenames, min_age_seconds=3600):
    """List photo files that no goods record uses.

    `used_filenames` is a set of names, e.g. from
    photo_repository.get_photo_filenames(). Files modified within the last
    `min_age_seconds` are skipped for safety.
    """
    if not PHOTO_DIR.exists():
        return []

    used = set(used_filenames)
    cutoff = time.time() - min_age_seconds
    unused = []

    for path in sorted(PHOTO_DIR.glob("*.jpg")):
        if not is_valid_photo_filename(path.name) or path.name in used:
            continue

        if path.stat().st_mtime <= cutoff:
            unused.append(path.name)

    return unused


def delete_unused_photos(used_filenames, min_age_seconds=3600):
    """Delete unused photos (and thumbnails). Returns how many were removed."""
    removed = 0

    for filename in find_unused_photos(used_filenames, min_age_seconds):
        if delete_goods_photo(filename):
            removed += 1

    return removed


if __name__ == "__main__":
    # Safe preview: list unused files without deleting anything.
    from photo_repository import get_photo_filenames

    unused = find_unused_photos(get_photo_filenames())

    print(f"Photo folder: {PHOTO_DIR}")

    if unused:
        print(f"{len(unused)} unused photo(s):")
        for name in unused:
            print(f"  {name}")
    else:
        print("No unused photos found.")

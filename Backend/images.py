import os

from PIL import Image, ImageOps

MAX_EDGE = 1600


def resize_file(path):
    """Shrink a stored upload in place. Animated GIFs are left unchanged."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".gif" or not os.path.isfile(path):
        return

    temp_path = path + ".resize"
    try:
        with Image.open(path) as image:
            if getattr(image, "n_frames", 1) > 1:
                return
            image = ImageOps.exif_transpose(image)
            image.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.LANCZOS)
            if ext in (".jpg", ".jpeg"):
                if image.mode not in ("RGB", "L"):
                    image = image.convert("RGB")
                image.save(temp_path, format="JPEG", quality=82, optimize=True)
            elif ext == ".webp":
                image.save(temp_path, format="WEBP", quality=80)
            elif ext == ".png":
                image.save(temp_path, format="PNG", optimize=True)
            else:
                return
        os.replace(temp_path, path)
    except Exception:
        if os.path.isfile(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass

import json
import os
from pathlib import Path

import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parent.parent
MATERIALS_DIR = ROOT_DIR / "WebsiteMaterials"
CLOUDINARY_ROOT = "iqgs/website-2026"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def configure_cloudinary() -> None:
    load_dotenv(ROOT_DIR / ".env")
    cloudinary.config(
        cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
        api_key=os.getenv("CLOUDINARY_API_KEY"),
        api_secret=os.getenv("CLOUDINARY_API_SECRET"),
        secure=True,
    )


def iter_assets() -> list[Path]:
    return sorted(
        path
        for path in MATERIALS_DIR.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )


def upload_asset(path: Path) -> dict:
    relative = path.relative_to(MATERIALS_DIR)
    public_id = f"{CLOUDINARY_ROOT}/{relative.with_suffix('').as_posix()}"
    result = cloudinary.uploader.upload(
        str(path),
        public_id=public_id,
        overwrite=True,
        resource_type="image",
        use_filename=False,
        unique_filename=False,
        invalidate=True,
    )
    return {
        "local_path": str(relative).replace("\\", "/"),
        "public_id": result["public_id"],
        "secure_url": result["secure_url"],
        "width": result.get("width"),
        "height": result.get("height"),
        "bytes": result.get("bytes"),
        "format": result.get("format"),
    }


def main() -> None:
    configure_cloudinary()
    assets = iter_assets()
    uploads = [upload_asset(path) for path in assets]
    print(json.dumps({"cloudinary_root": CLOUDINARY_ROOT, "uploads": uploads}, indent=2))


if __name__ == "__main__":
    main()

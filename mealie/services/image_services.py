import shutil
from pathlib import Path

import requests
from app_config import IMG_DIR
from urllib.parse import urlparse
from os.path import basename
from pathlib import Path
from utils.logger import logger


def read_image(recipe_slug: str) -> Path:
    if IMG_DIR.joinpath(recipe_slug).is_file():
        return IMG_DIR.joinpath(recipe_slug)
    else:
        recipe_slug = recipe_slug.split(".")[0]
        for file in IMG_DIR.glob(f"{recipe_slug}*"):
            return file


def write_image(recipe_slug: str, file_data: bytes, extension: str) -> Path.name:
    delete_image(recipe_slug)

    image_path = Path(IMG_DIR.joinpath(f"{recipe_slug}.{extension}"))
    with open(image_path, "ab") as f:
        f.write(file_data)

    return image_path


def delete_image(recipe_slug: str) -> str:
    recipe_slug = recipe_slug.split(".")[0]
    for file in IMG_DIR.glob(f"{recipe_slug}*"):
        return file.unlink()


def scrape_image(image_url: str, slug: str) -> Path:
    if isinstance(image_url, str):  # Handles String Types
        image_url = image_url

    if isinstance(image_url, list):  # Handles List Types
        image_url = image_url[0]

    if isinstance(image_url, dict):  # Handles Dictionary Types
        for key in image_url:
            if key == "url":
                image_url = image_url.get("url")

    #TODO: This could use a test
    extension = Path(urlparse(image_url).path).suffix
    filename = slug + "." + extension
    filename = IMG_DIR.joinpath(filename)

    try:
        r = requests.get(image_url, stream=True)
    except Exception as e:
        logger.error(f"Failed fetching image {e}")
        return

    if r.status_code == 200:
        with open(filename, "wb") as f:
            shutil.copyfileobj(r.raw, f)

        return filename

    return

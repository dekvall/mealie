import json
from pathlib import Path
from typing import List, Tuple

import extruct
import requests
import scrape_schema_recipe
import html
import re
from app_config import DEBUG_DIR
from slugify import slugify
from utils.logger import logger
from w3lib.html import get_base_url

from services.image_services import scrape_image
from services.recipe_services import Recipe

CWD = Path(__file__).parent
TEMP_FILE = DEBUG_DIR.joinpath("last_recipe.json")
STEP_SPLITTER = re.compile(r"(?:\d\. ?)|(?:[\n\r]+)")


def normalize_image_url(image) -> str:
    if type(image) == list:
        return image[0]
    elif type(image) == dict:
        return image["url"]
    elif type(image) == str:
        return image
    else:
        raise Exception(f"Unrecognised image URL format: {image}")


def normalize_instructions(instructions) -> List[dict]:
    if type(instructions) == str:
        return [
            {"text": unescape_html(line.strip())} for line in STEP_SPLITTER.split(instructions) if line
        ]

    # Plain strings in a list
    elif type(instructions) == list and type(instructions[0]) == str:
        return [{"text": unescape_html(step.strip())} for step in instructions]

    # Dictionaries (let's assume it's a HowToStep) in a list
    elif type(instructions) == list and type(instructions[0]) == dict:
        steps = instructions[0]["itemListElement"] if instructions[0]["@type"] == "HowToSection" else instructions
        return [
            {"text": unescape_html(step["text"].strip())}
            for step in steps
            if step["@type"] == "HowToStep"
    ]

    else:
        raise Exception(f"Unrecognised instruction format: {instructions}")


def unescape_html(l) -> str:
    if not l:
        return None
    # Some sites erroneously escape their strings on multiple levels
    while not l == (l := html.unescape(l)):
        pass
    return l


def normalize_yield(yld) -> str:
    if type(yld) == list:
        return yld[-1]
    else:
        return yld


def normalize_time(time_entry) -> str:
    if type(time_entry) == type(None):
        return None
    elif type(time_entry) != str:
        return str(time_entry)


def normalize_data(recipe_data: dict) -> dict:
    recipe_data["description"] = unescape_html(recipe_data.get("description"))
    recipe_data["totalTime"] = normalize_time(recipe_data.get("totalTime"))
    recipe_data["prepTime"] = normalize_time(recipe_data.get("prepTime"))
    recipe_data["performTime"] = normalize_time(recipe_data.get("performTime"))
    recipe_data["recipeYield"] = normalize_yield(recipe_data.get("recipeYield"))
    recipe_data["recipeInstructions"] = normalize_instructions(
        recipe_data["recipeInstructions"]
    )
    recipe_data["recipeIngredient"] = normalize_ingredients(recipe_data["recipeIngredient"])
    recipe_data["image"] = normalize_image_url(recipe_data.get("image"))
    return recipe_data


def normalize_ingredients(ingredients) -> List[str]:
    return [unescape_html(line.strip()) for line in ingredients]


def process_recipe_data(new_recipe: dict, url=None) -> dict:
    slug = slugify(new_recipe["name"])
    mealie_tags = {
        "slug": slug,
        "orgURL": url,
        "categories": [],
        "tags": [],
        "dateAdded": None,
        "notes": [],
        "extras": [],
    }

    new_recipe.update(mealie_tags)

    return new_recipe


def extract_recipe_from_html(html: str, url: str) -> dict:
    scraped_recipes: List[dict] = scrape_schema_recipe.loads(html, python_objects=True)

    if not scraped_recipes:
        scraped_recipes: List[dict] = scrape_schema_recipe.scrape_url(
            url, python_objects=True
        )

    if scraped_recipes:
        new_recipe: dict = scraped_recipes[0]
        logger.info(f"Recipe Scraped From Web: {new_recipe}")

        if not new_recipe:
            return "fail"  # TODO: Return Better Error Here

        new_recipe = process_recipe_data(new_recipe, url=url)
        new_recipe = normalize_data(new_recipe)
    else:
        new_recipe = basic_recipe_from_opengraph(html, url)
        logger.info(f"Recipe Scraped from opengraph metadata: {new_recipe}")

    return new_recipe


def download_image_for_recipe(recipe: dict) -> dict:
    try:
        img_path = scrape_image(recipe.get("image"), recipe.get("slug"))
        recipe["image"] = img_path.name
    except Exception as e:
        logger.error(f"{e}")
        recipe["image"] = None

    return recipe


def og_field(properties: dict, field_name: str) -> str:
    return next((val for name, val in properties if name == field_name), None)


def og_fields(properties: List[Tuple[str, str]], field_name: str) -> List[str]:
    return list({val for name, val in properties if name == field_name})


def basic_recipe_from_opengraph(html: str, url: str) -> dict:
    base_url = get_base_url(html, url)
    data = extruct.extract(html, base_url=base_url)
    properties = data["opengraph"][0]["properties"]
    return {
        "name": og_field(properties, "og:title"),
        "description": og_field(properties, "og:description"),
        "image": og_field(properties, "og:image"),
        "recipeYield": "",
        # FIXME: If recipeIngredient is an empty list, mongodb's data verification fails.
        "recipeIngredient": ["Could not detect ingredients"],
        # FIXME: recipeInstructions is allowed to be empty but message this is added for user sanity.
        "recipeInstructions": [{"text": "Could not detect instructions"}],
        "slug": slugify(og_field(properties, "og:title")),
        "orgURL": og_field(properties, "og:url"),
        "categories": [],
        "tags": og_fields(properties, "og:article:tag"),
        "dateAdded": None,
        "notes": [],
        "extras": [],
    }


def process_recipe_url(url: str) -> dict:
    r = requests.get(url)
    new_recipe = extract_recipe_from_html(r.text, url)
    new_recipe = download_image_for_recipe(new_recipe)
    return new_recipe


def create_from_url(url: str) -> Recipe:
    recipe_data = process_recipe_url(url)

    with open(TEMP_FILE, "w") as f:
        f.write(json.dumps(recipe_data, indent=4, default=str))

    recipe = Recipe(**recipe_data)

    return recipe

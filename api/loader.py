import re
from pathlib import Path
from typing import Any

import yaml

from api.models import Tool

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_YML = REPO_ROOT / "data.yml"
EXTENDED_DATA_YML = REPO_ROOT / "api" / "data" / "extended_data.yml"


def _slugify(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def load_landscape() -> dict[str, Any]:
    with DATA_YML.open() as f:
        return yaml.safe_load(f)


def load_extended_data() -> dict[str, Any]:
    default = {"contacts": {}, "use_cases": [], "naf_mappings": {}}
    if not EXTENDED_DATA_YML.exists():
        return default
    with EXTENDED_DATA_YML.open() as f:
        return yaml.safe_load(f) or default


def build_tools_index() -> dict[str, Tool]:
    landscape = load_landscape()
    index: dict[str, Tool] = {}
    for cat in landscape.get("categories", []):
        cat_name = cat["name"]
        for sub in cat.get("subcategories", []):
            sub_name = sub["name"]
            for item in sub.get("items", []):
                name = item["name"]
                slug = _slugify(name)
                extra = item.get("extra") or {}
                tags = extra.get("tag") or []
                if isinstance(tags, str):
                    tags = [tags]
                index[slug] = Tool(
                    name=name,
                    slug=slug,
                    category=cat_name,
                    subcategory=sub_name,
                    description=item.get("description"),
                    homepage_url=item.get("homepage_url"),
                    repo_url=item.get("repo_url"),
                    project=item.get("project"),
                    logo=item.get("logo"),
                    tags=tags,
                )
    return index

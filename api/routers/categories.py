from pathlib import Path

import yaml
from fastapi import APIRouter

from api.loader import load_landscape

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SETTINGS_YML = REPO_ROOT / "settings.yml"

router = APIRouter(tags=["categories"])


def _ordered_category_names() -> list[str]:
    with SETTINGS_YML.open() as f:
        settings = yaml.safe_load(f)
    groups = settings.get("groups") or []
    names: list[str] = []
    for g in groups:
        names.extend(g.get("categories") or [])
    return names


@router.get("/categories")
def list_categories() -> list[dict]:
    landscape = load_landscape()
    by_name = {c["name"]: c for c in landscape.get("categories", [])}
    out = []
    for name in _ordered_category_names():
        cat = by_name.get(name, {})
        subs = [s["name"] for s in cat.get("subcategories", [])]
        out.append({"name": name, "subcategories": subs})
    return out

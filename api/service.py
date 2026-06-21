"""Shared query core.

Both adapters call these functions:
  * the REST routers (api/routers/*)
  * the MCP tools (api/mcp_server.py)

Functions are HTTP-agnostic: single-item lookups return ``None`` when missing
(the caller decides whether that is a 404 or an error message), and list
queries always return a list. State is held in a cached ``Store`` so a single
process serves both surfaces from one in-memory copy of the data.
"""

from functools import lru_cache
from pathlib import Path

import yaml

from api.loader import build_tools_index, load_extended_data, load_landscape
from api.models import Contact, Tool, UseCase

SETTINGS_YML = Path(__file__).resolve().parent.parent / "settings.yml"


class Store:
    """In-memory snapshot of data.yml + sidecar extended data."""

    def __init__(self) -> None:
        self.tools: dict[str, Tool] = build_tools_index()
        self.extended: dict = load_extended_data()


@lru_cache(maxsize=1)
def get_store() -> Store:
    """Return the process-wide Store, building it on first access."""
    return Store()


# --- tools -----------------------------------------------------------------


def search_tools(
    store: Store,
    naf_component: str | None = None,
    category: str | None = None,
    project: str | None = None,
    q: str | None = None,
) -> list[Tool]:
    items = list(store.tools.values())
    if naf_component:
        items = [t for t in items if naf_component in t.tags]
    if category:
        items = [t for t in items if t.category == category]
    if project:
        items = [t for t in items if t.project == project]
    if q:
        ql = q.lower()
        items = [
            t
            for t in items
            if ql in t.name.lower()
            or (t.description and ql in t.description.lower())
        ]
    return items


def get_tool(store: Store, slug: str) -> Tool | None:
    return store.tools.get(slug)


def tool_contacts(store: Store, slug: str) -> list[Contact]:
    raw = store.extended.get("contacts", {}).get(slug, [])
    return [Contact(**c) for c in raw]


def tool_use_cases(store: Store, tool: Tool) -> list[UseCase]:
    raw = store.extended.get("use_cases", [])
    return [UseCase(**uc) for uc in raw if tool.name in uc.get("tools", [])]


# --- naf -------------------------------------------------------------------


def tools_for_naf(store: Store, component: str) -> list[Tool]:
    return [t for t in store.tools.values() if component in t.tags]


# --- use cases -------------------------------------------------------------


def list_use_cases(
    store: Store,
    tool: str | None = None,
    naf_component: str | None = None,
) -> list[UseCase]:
    use_cases = [UseCase(**uc) for uc in store.extended.get("use_cases", [])]
    if tool:
        use_cases = [uc for uc in use_cases if tool in uc.tools]
    if naf_component:
        use_cases = [uc for uc in use_cases if naf_component in uc.naf_components]
    return use_cases


def get_use_case(store: Store, id: str) -> UseCase | None:
    for uc in store.extended.get("use_cases", []):
        if uc.get("id") == id:
            return UseCase(**uc)
    return None


# --- categories ------------------------------------------------------------


def list_categories() -> list[dict]:
    with SETTINGS_YML.open() as f:
        settings = yaml.safe_load(f)
    ordered = []
    for g in settings.get("groups") or []:
        ordered.extend(g.get("categories") or [])

    landscape = load_landscape()
    by_name = {c["name"]: c for c in landscape.get("categories", [])}
    out = []
    for name in ordered:
        cat = by_name.get(name, {})
        subs = [s["name"] for s in cat.get("subcategories", [])]
        out.append({"name": name, "subcategories": subs})
    return out

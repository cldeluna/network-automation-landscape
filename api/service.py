"""Shared query core.

Both adapters call these functions:
  * the REST routers (api/routers/*)
  * the MCP tools (api/mcp_server.py)

Functions are HTTP-agnostic: single-item lookups return ``None`` when missing
(the caller decides whether that is a 404 or an error message), and list
queries always return a list. State is held in a cached ``Store`` so a single
process serves both surfaces from one in-memory copy of the data.
"""

import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote, urlencode

import yaml

from api.loader import build_tools_index, load_extended_data, load_landscape
from api.models import Contact, Tool, UseCaseLink

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


# --- naf -------------------------------------------------------------------


def tools_for_naf(store: Store, component: str) -> list[Tool]:
    return [t for t in store.tools.values() if component in t.tags]


# --- use cases (reference-only: link out to the external Use Case system) ---


def use_case_system_base_url(store: Store) -> str | None:
    """Base URL of the external Use Case system, or None if not configured.

    Env var ``UC_SYSTEM_URL`` overrides the sidecar
    ``use_case_system.base_url`` so it can be set per deployment.
    """
    env = os.environ.get("UC_SYSTEM_URL")
    if env:
        return env.rstrip("/")
    cfg = (store.extended.get("use_case_system") or {}).get("base_url")
    return cfg.rstrip("/") if cfg else None


def _link(
    store: Store,
    *,
    tool: str | None = None,
    naf_component: str | None = None,
    id: str | None = None,
) -> UseCaseLink:
    base = use_case_system_base_url(store)
    use_cases_url = None
    if base:
        if id is not None:
            use_cases_url = f"{base}/use-cases/{quote(id, safe='')}"
        else:
            params = {}
            if tool:
                params["tool"] = tool
            if naf_component:
                params["naf_component"] = naf_component
            use_cases_url = f"{base}/use-cases"
            if params:
                use_cases_url += "?" + urlencode(params)

    if base:
        note = "Use cases are hosted in a separate Use Case system; follow use_cases_url."
    else:
        note = (
            "Use cases are hosted in a separate Use Case system that is not yet "
            "configured. Set use_case_system.base_url (or the UC_SYSTEM_URL env "
            "var) to enable deep links."
        )

    return UseCaseLink(
        configured=base is not None,
        system_url=base,
        use_cases_url=use_cases_url,
        tool=tool,
        id=id,
        note=note,
    )


def use_cases_link(
    store: Store,
    tool: str | None = None,
    naf_component: str | None = None,
) -> UseCaseLink:
    return _link(store, tool=tool, naf_component=naf_component)


def use_case_link(store: Store, id: str) -> UseCaseLink:
    return _link(store, id=id)


def tool_use_cases_link(store: Store, tool: Tool) -> UseCaseLink:
    return _link(store, tool=tool.name)


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

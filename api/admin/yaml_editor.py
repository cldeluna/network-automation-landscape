"""Round-trip YAML editing.

Uses ruamel.yaml in round-trip mode so the ~2,300 lines of comments, ordering,
and the ``# yaml-language-server`` schema hint in data.yml are preserved when we
insert or update a single item. PyYAML would discard all of that.
"""

import io

from ruamel.yaml import YAML

from api.loader import _slugify


def _yaml() -> YAML:
    y = YAML()
    y.preserve_quotes = True
    y.width = 4096  # don't wrap long description/summary lines
    y.indent(mapping=2, sequence=4, offset=2)
    return y


def load_doc(text: str):
    """Parse YAML text into a round-trip document."""
    return _yaml().load(text)


def dump_doc(doc) -> str:
    """Serialize a round-trip document back to YAML text."""
    buf = io.StringIO()
    _yaml().dump(doc, buf)
    return buf.getvalue()


def _categories(doc):
    # landscape2 accepts either `categories` or `landscape` as the top key.
    cats = doc.get("categories")
    if cats is None:
        cats = doc.get("landscape")
    if cats is None:
        raise KeyError("data.yml has no 'categories' (or 'landscape') key")
    return cats


def _find_by_name(seq, name: str):
    for entry in seq or []:
        if entry.get("name") == name:
            return entry
    return None


def upsert_item(doc, category: str, subcategory: str, item: dict) -> str:
    """Insert or replace an item in data.yml, matched by slug.

    Returns "created" or "updated". Raises KeyError if the target
    category/subcategory does not exist (the caller validates choices first).
    """
    cat = _find_by_name(_categories(doc), category)
    if cat is None:
        raise KeyError(f"Unknown category: {category!r}")
    sub = _find_by_name(cat.get("subcategories"), subcategory)
    if sub is None:
        raise KeyError(f"Unknown subcategory: {subcategory!r} in {category!r}")

    items = sub.setdefault("items", [])
    slug = _slugify(item["name"])
    for i, existing in enumerate(items):
        if _slugify(existing.get("name", "")) == slug:
            items[i] = item
            return "updated"
    items.append(item)
    return "created"


def upsert_sidecar(doc, slug: str, fragment: dict) -> None:
    """Merge a tool's sidecar fragment into extended_data.yml in place.

    ``fragment`` is the output of ``ToolForm.to_sidecar()`` — optional
    ``contacts`` (list) and ``naf_mapping`` (dict). Empty pieces are skipped.
    """
    contacts = fragment.get("contacts")
    if contacts:
        bucket = doc.get("contacts")
        if not isinstance(bucket, dict):
            bucket = {}
            doc["contacts"] = bucket
        bucket[slug] = contacts

    naf_mapping = fragment.get("naf_mapping")
    if naf_mapping:
        bucket = doc.get("naf_mappings")
        if not isinstance(bucket, dict):
            bucket = {}
            doc["naf_mappings"] = bucket
        bucket[slug] = naf_mapping

    logo_url = fragment.get("logo_url")
    if logo_url:
        bucket = doc.get("logo_urls")
        if not isinstance(bucket, dict):
            bucket = {}
            doc["logo_urls"] = bucket
        bucket[slug] = logo_url

"""Self-service tool submission: HTML form -> GitHub PR against data.yml.

Routes (server-rendered, no JS framework):
  GET  /admin/tools/new          blank form
  GET  /admin/tools/{slug}/edit  form pre-filled from data.yml + sidecar
  POST /admin/tools              validate -> build PR (or preview when no token)
"""

import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from api.admin import github_pr, schema_validate
from api.admin import yaml_editor as ye
from api.admin.forms import (
    ALLOWED_TAGS,
    MATURITY_VALUES,
    SUMMARY_FIELDS,
    ToolForm,
)
from api.loader import (
    DATA_YML,
    EXTENDED_DATA_YML,
    _slugify,
    load_extended_data,
    load_landscape,
)
from api.models import NAF_TAXONOMY
from api.service import list_categories

router = APIRouter(tags=["admin"])

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

# Repo-relative paths the PR will write to (forward slashes for the git tree).
DATA_YML_REPO_PATH = "data.yml"
EXTENDED_DATA_REPO_PATH = "api/data/extended_data.yml"


def _choices() -> dict:
    """Dropdown/checkbox options for the form, derived from the live data."""
    cats = list_categories()  # [{name, subcategories: [...]}, ...]
    return {
        "categories": {c["name"]: c["subcategories"] for c in cats},
        "maturities": MATURITY_VALUES,
        "allowed_tags": ALLOWED_TAGS,
        "naf_taxonomy": NAF_TAXONOMY,
        "summary_fields": SUMMARY_FIELDS,
    }


def _find_raw(slug: str) -> tuple[str, str, dict] | None:
    """Locate a raw data.yml item by slug. Returns (category, subcategory, item)."""
    landscape = load_landscape()
    cats = landscape.get("categories") or landscape.get("landscape") or []
    for cat in cats:
        for sub in cat.get("subcategories", []):
            for item in sub.get("items", []):
                if _slugify(item.get("name", "")) == slug:
                    return cat["name"], sub["name"], item
    return None


def _prefill(slug: str) -> dict | None:
    """Build template prefill values for an existing tool (edit mode)."""
    found = _find_raw(slug)
    if found is None:
        return None
    category, subcategory, item = found
    extra = item.get("extra") or {}
    tags = extra.get("tag") or []
    if isinstance(tags, str):
        tags = [tags]
    summaries = {k: extra.get(k) for k in SUMMARY_FIELDS if extra.get(k)}

    sidecar = load_extended_data()
    contacts = (sidecar.get("contacts") or {}).get(slug, [])
    mapping = (sidecar.get("naf_mappings") or {}).get(slug, {})

    return {
        "name": item.get("name", ""),
        "category": category,
        "subcategory": subcategory,
        "description": item.get("description", ""),
        "homepage_url": item.get("homepage_url", ""),
        "repo_url": item.get("repo_url", ""),
        "logo": item.get("logo", ""),
        "project": item.get("project", ""),
        "crunchbase": item.get("crunchbase", ""),
        "twitter": item.get("twitter", ""),
        "tags": tags,
        "summaries": summaries,
        "contacts": contacts,
        "naf_component": mapping.get("naf_component", ""),
        "naf_subfunctions": mapping.get("naf_subfunctions", []),
        "secondary_naf_components": mapping.get("secondary_naf_components", []),
    }


def _render_form(
    request: Request,
    *,
    mode: str,
    values: dict,
    errors: list[str] | None = None,
    original_slug: str = "",
) -> HTMLResponse:
    ctx = {
        "mode": mode,
        "values": values,
        "errors": errors or [],
        "original_slug": original_slug,
        "choices": _choices(),
        "submit_token_required": bool(os.environ.get("SUBMIT_TOKEN")),
    }
    return TEMPLATES.TemplateResponse(request, "tool_form.html", ctx)


@router.get("/admin/tools/new", response_class=HTMLResponse)
def new_tool_form(request: Request) -> HTMLResponse:
    return _render_form(request, mode="new", values={})


@router.get("/admin/tools/{slug}/edit", response_class=HTMLResponse)
def edit_tool_form(slug: str, request: Request) -> HTMLResponse:
    values = _prefill(slug)
    if values is None:
        return HTMLResponse(f"Unknown tool: {slug}", status_code=404)
    return _render_form(request, mode="edit", values=values, original_slug=slug)


def _parse_form(form) -> dict:
    """Turn the raw multipart form into kwargs for ToolForm."""
    get = form.get

    def getlist(key):
        return [v for v in form.getlist(key) if v]

    summaries = {f: get(f) for f in SUMMARY_FIELDS if get(f)}

    # Contacts arrive as parallel arrays (one row each).
    contacts = []
    names = form.getlist("contact_name")
    roles = form.getlist("contact_role")
    emails = form.getlist("contact_email")
    githubs = form.getlist("contact_github")
    for i, cname in enumerate(names):
        if not cname.strip():
            continue
        contacts.append(
            {
                "name": cname.strip(),
                "role": (roles[i] if i < len(roles) else "") or None,
                "email": (emails[i] if i < len(emails) else "") or None,
                "github": (githubs[i] if i < len(githubs) else "") or None,
            }
        )

    return {
        "name": (get("name") or "").strip(),
        "category": get("category") or "",
        "subcategory": get("subcategory") or "",
        "description": (get("description") or "").strip() or None,
        "homepage_url": (get("homepage_url") or "").strip() or None,
        "repo_url": (get("repo_url") or "").strip() or None,
        "logo": (get("logo") or "").strip() or None,
        "project": (get("project") or "").strip() or None,
        "crunchbase": (get("crunchbase") or "").strip() or None,
        "twitter": (get("twitter") or "").strip() or None,
        "tags": getlist("tags"),
        "summaries": summaries,
        "contacts": contacts,
        "naf_component": (get("naf_component") or "").strip() or None,
        "naf_subfunctions": getlist("naf_subfunctions"),
        "secondary_naf_components": getlist("secondary_naf_components"),
        "submitter_name": (get("submitter_name") or "").strip(),
        "submitter_email": (get("submitter_email") or "").strip(),
    }


def _pr_body(tool: ToolForm, action: str, original_slug: str) -> str:
    lines = [
        f"Automated submission via the tool form ({action}).",
        "",
        f"- **Tool:** {tool.name}",
        f"- **Category:** {tool.category} / {tool.subcategory}",
        f"- **Submitted by:** {tool.submitter_name} <{tool.submitter_email}>",
    ]
    if action == "updated":
        lines.append(f"- **Edits existing tool:** `{original_slug}`")
    lines += ["", "Please review before merging.", "", "🤖 Generated via the self-service tool form."]
    return "\n".join(lines)


@router.post("/admin/tools", response_class=HTMLResponse)
async def submit_tool(request: Request) -> HTMLResponse:
    form = await request.form()
    raw = _parse_form(form)
    mode = form.get("mode") or "new"
    original_slug = form.get("original_slug") or ""

    # Optional shared-secret gate (anti-abuse for public self-service).
    required_token = os.environ.get("SUBMIT_TOKEN")
    if required_token and form.get("submit_token") != required_token:
        return _render_form(
            request, mode=mode, values=raw,
            errors=["Invalid or missing submit token."],
            original_slug=original_slug,
        )

    # 1. Validate the submission against the controlled vocabularies.
    try:
        tool = ToolForm(**raw)
    except ValidationError as exc:
        errs = [f"{' / '.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()]
        return _render_form(request, mode=mode, values=raw, errors=errs, original_slug=original_slug)

    # 2. Validate placement and add/edit identity against the live data.
    choices = _choices()
    if tool.category not in choices["categories"]:
        return _render_form(request, mode=mode, values=raw, errors=[f"Unknown category: {tool.category}"], original_slug=original_slug)
    if tool.subcategory not in choices["categories"][tool.category]:
        return _render_form(request, mode=mode, values=raw, errors=[f"Subcategory '{tool.subcategory}' is not in category '{tool.category}'"], original_slug=original_slug)

    slug = _slugify(tool.name)
    exists = _find_raw(slug) is not None
    if mode == "new" and exists:
        return _render_form(request, mode=mode, values=raw, errors=[f"A tool with slug '{slug}' already exists. Use the edit form."], original_slug=original_slug)
    if mode == "edit" and not exists:
        return _render_form(request, mode=mode, values=raw, errors=[f"No existing tool with slug '{slug}' to edit."], original_slug=original_slug)

    # 3. Apply the change to round-trip copies of the YAML files.
    data_text = DATA_YML.read_text()
    data_doc = ye.load_doc(data_text)
    action = ye.upsert_item(data_doc, tool.category, tool.subcategory, tool.to_data_item())
    new_data_text = ye.dump_doc(data_doc)

    sidecar = tool.to_sidecar()
    files = {DATA_YML_REPO_PATH: new_data_text}
    if sidecar:
        sc_doc = ye.load_doc(EXTENDED_DATA_YML.read_text())
        ye.upsert_sidecar(sc_doc, slug, sidecar)
        files[EXTENDED_DATA_REPO_PATH] = ye.dump_doc(sc_doc)

    # 4. Pre-flight schema validation (same schema CI uses).
    import yaml

    schema_errors = schema_validate.validate_landscape(yaml.safe_load(new_data_text))
    if schema_errors:
        return _render_form(request, mode=mode, values=raw, errors=["Schema validation failed:"] + schema_errors, original_slug=original_slug)

    # 5. Open a PR — or preview when GH_TOKEN is unset.
    cfg = github_pr.GitHubConfig.from_env()
    title = f"{'Update' if action == 'updated' else 'Add'} {tool.name} via tool form"
    body = _pr_body(tool, action, original_slug)

    if not cfg.configured:
        return TEMPLATES.TemplateResponse(
            request,
            "submitted.html",
            {
                "configured": False,
                "action": action,
                "tool_name": tool.name,
                "repo": cfg.repo,
                "preview": new_data_text_diff_preview(data_text, new_data_text),
                "files": list(files),
            },
        )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    branch = f"submit/{slug}-{timestamp}"
    try:
        pr = github_pr.open_pr(cfg, branch=branch, title=title, body=body, text_files=files)
    except github_pr.GitHubError as exc:
        return _render_form(request, mode=mode, values=raw, errors=[f"PR creation failed: {exc}"], original_slug=original_slug)

    return TEMPLATES.TemplateResponse(
        request,
        "submitted.html",
        {
            "configured": True,
            "action": action,
            "tool_name": tool.name,
            "repo": cfg.repo,
            "pr_url": pr.get("html_url"),
            "pr_number": pr.get("number"),
        },
    )


def new_data_text_diff_preview(old: str, new: str) -> str:
    """A unified diff of the data.yml change, for the no-token preview page."""
    import difflib

    diff = difflib.unified_diff(
        old.splitlines(), new.splitlines(),
        fromfile="data.yml (current)", tofile="data.yml (proposed)", lineterm="",
    )
    return "\n".join(diff)

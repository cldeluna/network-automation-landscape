from fastapi import APIRouter, HTTPException, Request

from api.models import Contact, Tool, UseCase

router = APIRouter(tags=["tools"])


def _tools(request: Request) -> dict[str, Tool]:
    return request.app.state.tools


def _extended(request: Request) -> dict:
    return request.app.state.extended


@router.get("/tools", response_model=list[Tool])
def list_tools(
    request: Request,
    naf_component: str | None = None,
    category: str | None = None,
    project: str | None = None,
    q: str | None = None,
) -> list[Tool]:
    items = list(_tools(request).values())
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


@router.get("/tools/{slug}", response_model=Tool)
def get_tool(slug: str, request: Request) -> Tool:
    tool = _tools(request).get(slug)
    if tool is None:
        raise HTTPException(status_code=404, detail=f"Tool '{slug}' not found")
    return tool


@router.get("/tools/{slug}/contacts", response_model=list[Contact])
def list_contacts(slug: str, request: Request) -> list[Contact]:
    if slug not in _tools(request):
        raise HTTPException(status_code=404, detail=f"Tool '{slug}' not found")
    contacts = _extended(request).get("contacts", {}).get(slug, [])
    return [Contact(**c) for c in contacts]


@router.get("/tools/{slug}/use_cases", response_model=list[UseCase])
def list_tool_use_cases(slug: str, request: Request) -> list[UseCase]:
    tool = _tools(request).get(slug)
    if tool is None:
        raise HTTPException(status_code=404, detail=f"Tool '{slug}' not found")
    use_cases = _extended(request).get("use_cases", [])
    return [UseCase(**uc) for uc in use_cases if tool.name in uc.get("tools", [])]

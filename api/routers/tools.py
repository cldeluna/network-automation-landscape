from fastapi import APIRouter, HTTPException, Request

from api import service
from api.models import Contact, Tool, UseCase

router = APIRouter(tags=["tools"])


@router.get("/tools", response_model=list[Tool])
def list_tools(
    request: Request,
    naf_component: str | None = None,
    category: str | None = None,
    project: str | None = None,
    q: str | None = None,
) -> list[Tool]:
    return service.search_tools(
        request.app.state.store,
        naf_component=naf_component,
        category=category,
        project=project,
        q=q,
    )


@router.get("/tools/{slug}", response_model=Tool)
def get_tool(slug: str, request: Request) -> Tool:
    tool = service.get_tool(request.app.state.store, slug)
    if tool is None:
        raise HTTPException(status_code=404, detail=f"Tool '{slug}' not found")
    return tool


@router.get("/tools/{slug}/contacts", response_model=list[Contact])
def list_contacts(slug: str, request: Request) -> list[Contact]:
    store = request.app.state.store
    if service.get_tool(store, slug) is None:
        raise HTTPException(status_code=404, detail=f"Tool '{slug}' not found")
    return service.tool_contacts(store, slug)


@router.get("/tools/{slug}/use_cases", response_model=list[UseCase])
def list_tool_use_cases(slug: str, request: Request) -> list[UseCase]:
    store = request.app.state.store
    tool = service.get_tool(store, slug)
    if tool is None:
        raise HTTPException(status_code=404, detail=f"Tool '{slug}' not found")
    return service.tool_use_cases(store, tool)

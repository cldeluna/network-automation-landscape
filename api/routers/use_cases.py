from fastapi import APIRouter, Request

from api import service
from api.models import UseCaseLink

router = APIRouter(tags=["use_cases"])


@router.get("/use_cases", response_model=UseCaseLink)
def use_cases(
    request: Request,
    tool: str | None = None,
    naf_component: str | None = None,
) -> UseCaseLink:
    """Use cases live in a separate Use Case system. This returns a link out to
    it (optionally filtered by tool / naf_component), not embedded content."""
    return service.use_cases_link(
        request.app.state.store, tool=tool, naf_component=naf_component
    )


@router.get("/use_cases/{id}", response_model=UseCaseLink)
def get_use_case(id: str, request: Request) -> UseCaseLink:
    """Deep link to a single use case in the external Use Case system."""
    return service.use_case_link(request.app.state.store, id)

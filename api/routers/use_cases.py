from fastapi import APIRouter, HTTPException, Request

from api import service
from api.models import UseCase

router = APIRouter(tags=["use_cases"])


@router.get("/use_cases", response_model=list[UseCase])
def list_use_cases(
    request: Request,
    tool: str | None = None,
    naf_component: str | None = None,
) -> list[UseCase]:
    return service.list_use_cases(
        request.app.state.store, tool=tool, naf_component=naf_component
    )


@router.get("/use_cases/{id}", response_model=UseCase)
def get_use_case(id: str, request: Request) -> UseCase:
    uc = service.get_use_case(request.app.state.store, id)
    if uc is None:
        raise HTTPException(status_code=404, detail=f"Use case '{id}' not found")
    return uc

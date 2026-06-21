from fastapi import APIRouter, HTTPException, Request

from api.models import UseCase

router = APIRouter(tags=["use_cases"])


@router.get("/use_cases", response_model=list[UseCase])
def list_use_cases(
    request: Request,
    tool: str | None = None,
    naf_component: str | None = None,
) -> list[UseCase]:
    raw = request.app.state.extended.get("use_cases", [])
    use_cases = [UseCase(**uc) for uc in raw]
    if tool:
        use_cases = [uc for uc in use_cases if tool in uc.tools]
    if naf_component:
        use_cases = [uc for uc in use_cases if naf_component in uc.naf_components]
    return use_cases


@router.get("/use_cases/{id}", response_model=UseCase)
def get_use_case(id: str, request: Request) -> UseCase:
    raw = request.app.state.extended.get("use_cases", [])
    for uc in raw:
        if uc.get("id") == id:
            return UseCase(**uc)
    raise HTTPException(status_code=404, detail=f"Use case '{id}' not found")

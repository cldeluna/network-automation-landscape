from fastapi import APIRouter, HTTPException, Request

from api.models import NAF_TAXONOMY, Tool

router = APIRouter(tags=["naf"])


@router.get("/naf")
def get_naf_taxonomy() -> dict[str, list[str]]:
    return NAF_TAXONOMY


@router.get("/naf/{component}", response_model=list[Tool])
def tools_for_component(component: str, request: Request) -> list[Tool]:
    if component not in NAF_TAXONOMY:
        raise HTTPException(
            status_code=404, detail=f"Unknown NAF component '{component}'"
        )
    return [t for t in request.app.state.tools.values() if component in t.tags]

from fastapi import APIRouter

from api import service

router = APIRouter(tags=["categories"])


@router.get("/categories")
def list_categories() -> list[dict]:
    return service.list_categories()

from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.loader import build_tools_index, load_extended_data
from api.routers import categories, naf, tools, use_cases


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.tools = build_tools_index()
    app.state.extended = load_extended_data()
    yield


app = FastAPI(
    title="Network Automation Landscape API",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(tools.router, prefix="/api/v1")
app.include_router(naf.router, prefix="/api/v1")
app.include_router(use_cases.router, prefix="/api/v1")
app.include_router(categories.router, prefix="/api/v1")

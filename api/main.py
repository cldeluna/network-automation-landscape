from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.mcp_server import mcp
from api.routers import categories, naf, tools, use_cases
from api.service import get_store

# MCP served over Streamable HTTP. Inner path is "/"; we mount it at /mcp
# below, so the public endpoint is /mcp.
mcp_app = mcp.http_app(path="/")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm the shared store, then run the MCP session-manager lifespan so the
    # mounted MCP app works. Both surfaces read this one in-memory copy.
    app.state.store = get_store()
    async with mcp_app.lifespan(app):
        yield


app = FastAPI(
    title="Network Automation Landscape API",
    version="0.1.0",
    lifespan=lifespan,
)

# Wide-open CORS for public testing. Lock this down to specific origins
# before this is anything more than a throwaway test deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(tools.router, prefix="/api/v1")
app.include_router(naf.router, prefix="/api/v1")
app.include_router(use_cases.router, prefix="/api/v1")
app.include_router(categories.router, prefix="/api/v1")

# REST lives under /api/v1; MCP (Streamable HTTP) is mounted at /mcp.
app.mount("/mcp", mcp_app)

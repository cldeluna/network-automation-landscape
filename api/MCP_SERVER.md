# MCP Server

An [MCP](https://modelcontextprotocol.io) server that exposes the network
automation landscape (the data in `data.yml`) to LLM agents such as Claude. It
runs over **Streamable HTTP** and is served by the **same FastAPI process** as
the REST API, mounted at `/mcp`.

---

## What we did

We added an MCP surface *alongside* the existing read-only REST API without
duplicating logic. The design is **one shared query core + two thin adapters**:

```
api/
  loader.py        # parse data.yml + sidecar extended_data.yml, build indexes
  service.py       # SHARED query core — pure, HTTP-agnostic functions
  models.py        # Pydantic types (Tool, Contact, UseCase) + NAF taxonomy
  routers/*        # REST adapter   -> calls service.*   (mounted at /api/v1)
  mcp_server.py    # MCP adapter    -> calls service.*   (mounted at /mcp)
  main.py          # FastAPI app: REST routers + mounted MCP app + lifespans
```

Key points:

- **Both surfaces call `api/service.py`**, so REST and MCP can never return
  different answers for the same query.
- **One in-memory copy of the data.** `service.get_store()` is cached
  (`lru_cache`), so the single uvicorn process serves REST and MCP from the same
  `Store`. `data.yml` is read once at startup.
- **MCP tools are hand-written** (not auto-generated from the REST routes) so
  their descriptions are written for an LLM to choose the right tool. They are
  thin wrappers that call `service.*` and return plain dicts.
- **Mounted on the same app.** `api/main.py` builds the MCP ASGI app with
  `mcp.http_app(path="/")`, mounts it at `/mcp`, and combines the data-warming
  lifespan with the MCP session-manager lifespan.

Use REST only, MCP only, or both — they are independent endpoints on one
service. Because the core is isolated, splitting into two separate deployments
later (e.g. for different auth) is a deploy-config change, not a rewrite.

---

## Supported MCP tools

All tools are defined in `api/mcp_server.py` and back onto `api/service.py`.

| Tool | Arguments | Returns |
|------|-----------|---------|
| `search_tools` | `naf_component?`, `category?`, `project?`, `q?` (all optional, AND-combined) | List of matching tools |
| `get_tool` | `slug` (e.g. `netbox-community`) | One tool record, or `{"error": ...}` if not found |
| `tools_by_naf_component` | `component` (one of the 7 NAF components) | All tools tagged to that component |
| `naf_taxonomy` | — | The 7 NAF components mapped to their sub-functions |
| `list_use_cases` | `tool?`, `naf_component?` | Use cases (from the sidecar; empty until populated) |
| `list_categories` | — | Landscape categories + subcategories, in display order |

Valid `naf_component` values: `presentation`, `observability`, `orchestration`,
`intent`, `collector`, `executor`, `network_infrastructure`.

### Relationship to the REST endpoints

The MCP tools mirror the REST API (both over `api/service.py`):

| MCP tool | Equivalent REST endpoint |
|----------|--------------------------|
| `search_tools` | `GET /api/v1/tools` (`naf_component`, `category`, `project`, `q`) |
| `get_tool` | `GET /api/v1/tools/{slug}` |
| `tools_by_naf_component` | `GET /api/v1/naf/{component}` |
| `naf_taxonomy` | `GET /api/v1/naf` |
| `list_use_cases` | `GET /api/v1/use_cases` (`tool`, `naf_component`) |
| `list_categories` | `GET /api/v1/categories` |

> Note: the per-tool contact and use-case REST endpoints
> (`/api/v1/tools/{slug}/contacts`, `/api/v1/tools/{slug}/use_cases`) are not yet
> exposed as dedicated MCP tools. Add them to `mcp_server.py` if an agent needs
> them.

---

## Dependencies added

In `pyproject.toml`:

| Package | Where | Why |
|---------|-------|-----|
| `fastmcp>=3.4.2` | runtime | MCP server framework; provides `FastMCP`, `@mcp.tool`, and the Streamable HTTP ASGI app (`http_app`) |
| `pytest-asyncio>=1.4.0` | dev | Run the async MCP client tests |

Plus pytest config in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

Install everything with:

```bash
uv sync
```

---

## Run it locally

The MCP server is not a separate process — start the API and you get both:

```bash
uv run uvicorn api.main:app --reload --port 8001
```

- REST → <http://127.0.0.1:8001/api/v1/...>
- MCP  → <http://127.0.0.1:8001/mcp> (Streamable HTTP)

> `data.yml` is read once at startup. After editing it, restart uvicorn —
> `--reload` only restarts on `.py` changes.

### Try it from Python (fastmcp client)

```bash
uv run python -c "
import asyncio
from fastmcp import Client
async def main():
    async with Client('http://127.0.0.1:8001/mcp') as c:
        print([t.name for t in await c.list_tools()])
        res = await c.call_tool('search_tools', {'naf_component': 'intent'})
        print(res.structured_content)
asyncio.run(main())
"
```

### Inspect interactively

```bash
npx @modelcontextprotocol/inspector
# In the UI: Transport = Streamable HTTP, URL = http://127.0.0.1:8001/mcp
```

### Connect from Claude Code

```bash
# local
claude mcp add --transport http nal http://127.0.0.1:8001/mcp

# deployed
claude mcp add --transport http nal https://nal-api.onrender.com/mcp
```

### Tests

```bash
uv run pytest -q          # full suite (REST + MCP)
uv run pytest api/tests/test_mcp.py -v
```

---

## Run it on Render

This branch (`feature/mcp-server`) is built **on top of** the REST API branch,
so its app serves **both** surfaces from one process — deploying it gives you
REST *and* MCP. The MCP server is mounted on the same FastAPI app, so the start
command is unchanged:

```yaml
startCommand: "uv run uvicorn api.main:app --host 0.0.0.0 --port $PORT"
```

### Current deployment

The Render service **`nal-api`** is pointed at this branch (`feature/mcp-server`)
and serves **both** surfaces from one process:

- REST → `https://nal-api.onrender.com/api/v1/...`
- MCP  → `https://nal-api.onrender.com/mcp`

`feature/fastapi-phase-1` remains a REST-only branch for its PR; it is not
separately deployed. The single `nal-api` service runs the superset (this
branch), so one URL covers everything.

> To (re)create from scratch: Render dashboard → **New → Blueprint** → pick the
> repo → select branch `feature/mcp-server`. It reads this `render.yaml` and
> deploys the `nal-api` service.

When `feature/mcp-server` eventually merges to `main`, point `nal-api` at `main`.

### Caveats

- **No auth.** CORS is wide-open and there is no authentication on either
  surface — same as the REST API. Fine for testing; lock down before real use.
- **Cold starts.** Render's free plan spins down after ~15 min idle; the first
  request (REST or MCP) after that incurs a ~30s cold start.
- **Free-tier limits.** `nal-api` runs on the free plan; free instance-hours are
  shared across your Render account.
- **Auto-deploy.** `autoDeploy: true` is set, so every push to
  `feature/mcp-server` redeploys `nal-api` automatically.
- **Data refresh.** `data.yml` is read once at startup. After editing it, trigger
  a manual redeploy (or push) — a running instance won't pick up data changes on
  its own.
- **Stateless HTTP.** The server runs in the default Streamable HTTP mode. If you
  later move to a multi-instance Render plan, revisit MCP session handling.

### Branch / PR workflow

`feature/mcp-server` is built on top of `feature/fastapi-phase-1`, so it
**contains all of the REST commits** plus the MCP work. When opening PRs against
`main`:

1. Merge the **REST PR** (`feature/fastapi-phase-1`) first.
2. The **MCP PR** (`feature/mcp-server`) then shows only the MCP-specific diff.
3. If you squash/rebase the REST PR, rebase `feature/mcp-server` onto the updated
   `main` afterward so its history stays clean.

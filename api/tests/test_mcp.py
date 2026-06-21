import pytest
from fastmcp import Client

from api.mcp_server import mcp


def _unwrap(result):
    """fastmcp wraps list returns as {'result': [...]} in structured_content."""
    data = result.structured_content if result.structured_content is not None else result.data
    if isinstance(data, dict) and set(data.keys()) == {"result"}:
        return data["result"]
    return data


@pytest.fixture
async def mcp_client():
    async with Client(mcp) as c:
        yield c


async def test_tools_registered(mcp_client):
    names = {t.name for t in await mcp_client.list_tools()}
    assert {
        "search_tools",
        "get_tool",
        "tools_by_naf_component",
        "naf_taxonomy",
        "use_cases_link",
        "list_categories",
    }.issubset(names)


async def test_use_cases_link(mcp_client):
    body = _unwrap(await mcp_client.call_tool("use_cases_link", {}))
    assert body["source"] == "external"
    assert "configured" in body


async def test_search_tools_filter(mcp_client):
    res = await mcp_client.call_tool("search_tools", {"naf_component": "intent"})
    items = _unwrap(res)
    assert len(items) > 0
    assert all("intent" in t["tags"] for t in items)


async def test_get_tool_found_and_missing(mcp_client):
    res = await mcp_client.call_tool("search_tools", {})
    slug = _unwrap(res)[0]["slug"]

    found = _unwrap(await mcp_client.call_tool("get_tool", {"slug": slug}))
    assert found["slug"] == slug

    missing = _unwrap(await mcp_client.call_tool("get_tool", {"slug": "nope-xyz"}))
    assert "error" in missing


async def test_naf_taxonomy(mcp_client):
    tax = _unwrap(await mcp_client.call_tool("naf_taxonomy", {}))
    assert "intent" in tax and "executor" in tax


def test_mcp_route_mounted():
    """The MCP app is mounted on the FastAPI app at /mcp."""
    from api.main import app

    mounts = [r.path for r in app.routes if getattr(r, "path", "") == "/mcp"]
    assert mounts, "expected an MCP mount at /mcp"

"""MCP adapter (Streamable HTTP).

A thin surface over ``api.service`` — the exact same query core the REST API
uses, so the two can never drift. Tool descriptions are written for an LLM
client: they explain what each tool returns and when to reach for it.

Mounted onto the FastAPI app in ``api.main`` at ``/mcp``.
"""

from fastmcp import FastMCP

from api import service
from api.models import NAF_TAXONOMY

mcp = FastMCP("network-automation-landscape")


@mcp.tool
def search_tools(
    naf_component: str | None = None,
    category: str | None = None,
    project: str | None = None,
    q: str | None = None,
) -> list[dict]:
    """Search the network automation tool catalog.

    All filters are optional and combine with AND. Returns matching tools with
    their name, slug, category, maturity (project), and NAF tags.

    Args:
        naf_component: NAF tag to filter by, e.g. "intent", "executor",
            "observability", "collector", "orchestration", "presentation".
        category: Landscape category, e.g. "Network state", "Automation Tooling".
        project: Maturity / business model, e.g. "full-open-source",
            "commercial-only", "saas".
        q: Free-text match against tool name and description.
    """
    tools = service.search_tools(
        service.get_store(),
        naf_component=naf_component,
        category=category,
        project=project,
        q=q,
    )
    return [t.model_dump() for t in tools]


@mcp.tool
def get_tool(slug: str) -> dict:
    """Get a single tool by its slug (lowercase, hyphenated name).

    Example slug: "netbox-community". Returns the full tool record, or an
    error dict if no tool matches.
    """
    tool = service.get_tool(service.get_store(), slug)
    if tool is None:
        return {"error": f"Tool '{slug}' not found"}
    return tool.model_dump()


@mcp.tool
def tools_by_naf_component(component: str) -> list[dict]:
    """List every tool tagged to a NAF component.

    Valid components: presentation, observability, orchestration, intent,
    collector, executor, network_infrastructure. Use `naf_taxonomy` to see the
    sub-functions of each.
    """
    if component not in NAF_TAXONOMY:
        return [{"error": f"Unknown NAF component '{component}'"}]
    return [t.model_dump() for t in service.tools_for_naf(service.get_store(), component)]


@mcp.tool
def naf_taxonomy() -> dict[str, list[str]]:
    """Return the full NAF (Network Automation Framework) taxonomy:
    the 7 components mapped to their sub-functions."""
    return NAF_TAXONOMY


@mcp.tool
def list_use_cases(
    tool: str | None = None, naf_component: str | None = None
) -> list[dict]:
    """List network automation use cases, optionally filtered.

    Args:
        tool: Only use cases that reference this tool name (exact name, not slug).
        naf_component: Only use cases exercising this NAF component.
    """
    use_cases = service.list_use_cases(
        service.get_store(), tool=tool, naf_component=naf_component
    )
    return [uc.model_dump() for uc in use_cases]


@mcp.tool
def list_categories() -> list[dict]:
    """List the landscape categories and their subcategories, in display order."""
    return service.list_categories()

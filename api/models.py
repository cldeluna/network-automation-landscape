from enum import Enum

from pydantic import BaseModel


class NAFComponent(str, Enum):
    presentation = "presentation"
    observability = "observability"
    orchestration = "orchestration"
    intent = "intent"
    collector = "collector"
    executor = "executor"
    network_infrastructure = "network_infrastructure"


NAF_TAXONOMY: dict[str, list[str]] = {
    "presentation": ["Dashboards", "CLI", "ITSM Integration", "API Gateway", "ChatOps"],
    "observability": ["Observed State", "Observed Logic & Analytics"],
    "orchestration": ["Workflows", "Events", "Scheduling", "Rollback"],
    "intent": ["Intended State / SoT", "Intended Logic & Validation"],
    "collector": ["Read Ops", "Data Normalization"],
    "executor": ["Write Ops", "Idempotent", "Dry-Run"],
    "network_infrastructure": [
        "Routers",
        "Switches",
        "Firewalls",
        "LB",
        "SD-WAN",
        "Cloud Fabric",
    ],
}


class Contact(BaseModel):
    name: str
    role: str | None = None
    email: str | None = None
    github: str | None = None
    voluntary: bool = True


class UseCaseLink(BaseModel):
    """A pointer into the external Use Case system.

    The landscape does not store use-case content or the tool->use-case mapping;
    that lives in a separate Use Case system. These endpoints return a link out
    to it. When the system's base URL is not configured, ``configured`` is False
    and the URL fields are null.
    """

    source: str = "external"
    configured: bool
    system_url: str | None = None
    use_cases_url: str | None = None
    tool: str | None = None
    id: str | None = None
    note: str


class Tool(BaseModel):
    name: str
    slug: str
    category: str
    subcategory: str
    description: str | None = None
    homepage_url: str | None = None
    repo_url: str | None = None
    project: str | None = None
    logo: str | None = None
    tags: list[str] = []
    # Formal NAF classification. Derived from ``tags`` (first tag = primary,
    # the rest = secondary), with per-tool overrides from the sidecar
    # ``naf_mappings`` in extended_data.yml.
    naf_component: str | None = None
    naf_subfunctions: list[str] = []
    secondary_naf_components: list[str] = []

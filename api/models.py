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


class UseCase(BaseModel):
    id: str
    title: str
    description: str
    tools: list[str]
    naf_components: list[str]
    actor: str


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

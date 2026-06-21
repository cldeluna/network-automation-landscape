# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A curated YAML-driven landscape visualization of network automation tools, built on
[`cncf/landscape2`](https://github.com/cncf/landscape2). The rendered site lives at
https://steinzi.com/network-automation-landscape/. This fork extends the project by
adding a **FastAPI layer** on top of the existing YAML data so the catalog can be
queried programmatically.

The static landscape (landscape2 build) and the FastAPI service are **independent
deliverables** that share the same source data (`data.yml`). Do not modify the
landscape2 build pipeline when working on the API.

## Existing data model (`data.yml`)

The top-level structure is:

```
categories:
  - name: <category>
    subcategories:
      - name: <subcategory>
        items:
          - name, description, homepage_url, logo, project, repo_url, ...
            extra:
              tag: [<naf_tag>, ...]
              summary_use_case: ...
              summary_business_use_case: ...
              summary_integration: ...
              summary_tags: ...
              summary_personas: ...
              accepted: <date>
              documentation_url: ...
```

**`project` field** — maturity/license classifier. Values: `full-open-source`,
`oss-with-paid-support`, `freemium`, `commercial-with-trial`, `commercial-only`,
`enterprise`, `saas`, `hybrid`, `inactive`, `deprecated`, `end-of-life`, `archived`,
`free-restrictive`, `closed-core`.

**`extra.tag`** — loose NAF alignment tags already in the data. Current values in use:
`intent`, `observability`, `collector`, `orchestration`, `executor`, `presentation`,
`lab`, `tool`. These are the primary basis for NAF-block queries in the API.

**Nine landscape categories** (from `settings.yml`): Network state, Telemetry and
observability, Automation Tooling, Security, Labbing, Terraform Eco-System, Python
Eco-System, GoLang Eco-System, Reporting & Insights, AI Ecosystem.

## NAF taxonomy (controlled vocabulary for the API)

The seven NAF (Network Automation Framework) components used as the formal taxonomy:

| NAF Component       | Sub-functions |
|---------------------|---------------|
| Presentation        | Dashboards, CLI, ITSM Integration, API Gateway, ChatOps |
| Observability       | Observed State, Observed Logic & Analytics |
| Orchestration       | Workflows, Events, Scheduling, Rollback |
| Intent              | Intended State / SoT, Intended Logic & Validation |
| Collector           | Read Ops, Data Normalization |
| Executor            | Write Ops, Idempotent, Dry-Run |
| Network Infrastructure | Routers, Switches, Firewalls, LB, SD-WAN, Cloud Fabric |

The `extra.tag` values in `data.yml` map roughly to these components (e.g. `intent` →
Intent, `executor` → Executor). The API formalizes this mapping. Tools that do not fit
NAF (e.g. labbing tools like Containerlab) are tagged `lab` and the API exposes them
under a separate `naf_component: null` / `lab: true` path.

## FastAPI project — purpose and scope

**Goal:** Add read-only API endpoints on top of `data.yml` so external tools can query
the landscape by NAF block, find contacts for a tool, or discover use cases that
reference a tool. A later phase adds CRUD.

**Data source for Phase 1:** Parse `data.yml` at startup into in-memory structures.
No database required for Phase 1. The YAML is the source of truth.

**Phase 2:** Migrate to Dolt (versioned MySQL-wire SQL) for CRUD and audit trail.

### New fields the API layer adds (not yet in `data.yml`)

These fields do not exist in the upstream landscape data. They live in a sidecar file
(e.g. `api/extended_data.yml` or a Dolt table) keyed by `item.name`:

| Field | Type | Description |
|-------|------|-------------|
| `contacts` | list of Contact | Voluntary community contacts for the tool |
| `use_cases` | list of UseCase ref | Use cases (by ID) that reference this tool |
| `naf_component` | enum (7 values) | Formal NAF classification (primary) |
| `naf_subfunctions` | list of str | NAF sub-functions within the primary component |
| `secondary_naf_components` | list of str | Secondary NAF placements (many tools span blocks) |

**Contact schema:**
```python
class Contact(BaseModel):
    name: str
    role: str | None = None          # e.g. "maintainer", "community volunteer"
    email: str | None = None
    github: str | None = None
    voluntary: bool = True           # all contacts are opt-in
```

**UseCase schema:**
```python
class UseCase(BaseModel):
    id: str                          # e.g. "UC-001"
    title: str
    description: str
    tools: list[str]                 # list of tool names from data.yml
    naf_components: list[str]        # NAF components exercised
    actor: str                       # primary actor, e.g. "Network Engineer"
```

## FastAPI endpoints (Phase 1 — read-only)

All endpoints are under `/api/v1/`. Responses are JSON.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/tools` | List all tools. Query params: `naf_component`, `naf_subfunction`, `category`, `project` (maturity), `q` (free-text search across name/description/tags) |
| GET | `/tools/{name}` | Single tool record by name (slug or exact match) |
| GET | `/tools/{name}/contacts` | Voluntary contacts for a tool |
| GET | `/tools/{name}/use_cases` | Use cases that reference this tool |
| GET | `/naf` | Full NAF taxonomy (components + sub-functions) |
| GET | `/naf/{component}` | All tools tagged to a NAF component |
| GET | `/categories` | Landscape categories and subcategories (mirrors `settings.yml`) |
| GET | `/use_cases` | All use cases. Query param: `tool`, `naf_component` |
| GET | `/use_cases/{id}` | Single use case by ID |
| GET | `/health` | Health check |

**Phase 2 additions** (CRUD, authenticated):

| Method | Path | Description |
|--------|------|-------------|
| POST | `/tools` | Add a tool |
| PATCH | `/tools/{name}` | Update a tool |
| DELETE | `/tools/{name}` | Soft-delete a tool |
| POST | `/tools/{name}/contacts` | Add a contact |
| POST | `/use_cases` | Add a use case |

## Key design decisions

- **`data.yml` is read-only from the API's perspective in Phase 1.** The API reads it;
  it does not write back. Extended data (contacts, use cases, formal NAF mapping) lives
  in a sidecar file the API owns.
- **Tool identity key is `name` from `data.yml`.** Use a normalized slug (lowercase,
  spaces → hyphens) for URL paths. Keep the original `name` for display.
- **NAF tag → component mapping:** The `extra.tag` list in `data.yml` seeds the
  `naf_component` field in the extended data. When a tool has multiple tags, the first
  tag is `naf_component` (primary) and the rest are `secondary_naf_components`.
- **Contacts are voluntary and opt-in.** Never infer contacts from repo metadata.
  The contact list starts empty and is populated only through explicit submissions.
- **Use cases reference tools by name**, not by a foreign key, so they survive tool
  renames gracefully.

## Differences from the upstream repo

| Aspect | Upstream (steinzi) | This fork |
|--------|--------------------|-----------|
| API | None (static site) | FastAPI service under `api/` |
| NAF mapping | Loose `extra.tag` strings | Formal enum + sub-functions |
| Contacts | Not present | Sidecar extended data |
| Use cases | Not present | Sidecar + API endpoints |
| Data store | `data.yml` only | Phase 1: YAML; Phase 2: Dolt |

## Suggested repo layout for the API addition

```
api/
  main.py              # FastAPI app, lifespan loads data.yml + extended_data.yml
  models.py            # Pydantic models (Tool, Contact, UseCase, NAFComponent)
  routers/
    tools.py
    naf.py
    use_cases.py
  data/
    extended_data.yml  # contacts, use_cases, formal NAF mappings (sidecar)
  tests/
    test_tools.py
    test_naf.py
    test_use_cases.py
pyproject.toml         # add fastapi, uvicorn, pyyaml, pydantic
```

## Commands (once pyproject.toml is set up)

```bash
# Install deps
uv sync

# Run the API locally
uv run uvicorn api.main:app --reload

# Run tests
uv run pytest api/tests/

# Validate data.yml parses cleanly
uv run python -c "import yaml; yaml.safe_load(open('data.yml'))"
```

## Context for this work

This FastAPI layer was designed in a prior Claude Code session working from the repo at
`automation_tool_sources`. The full spec is in that repo at
`plans/help-me-write-a-linked-rain.md`. Key references from that session:

- Seed data sources: https://packetpushers.net/blog/open-source-networking-projects/ and this landscape
- The NAF diagram is at `automation_tool_sources/images/naf_framework_components.png`
- Eventual UI: Streamlit consuming these same API endpoints
- Eventual DB: Dolt (MySQL wire protocol), migrated from YAML in Phase 2

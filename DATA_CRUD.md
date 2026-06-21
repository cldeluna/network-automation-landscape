# DATA_CRUD — Self-service tool submission (web form → GitHub PR)

Branch: **`feature/admin-crud-form`** (built on `feature/mcp-server`).

This branch adds a **user-friendly way to add/edit catalog tools** without hand-editing
the ~2,300-line `data.yml`. A contributor fills an HTML form; the app validates the
submission against the **real landscape2 schema**, then opens a **GitHub pull request**
against `data.yml` (and the `extended_data.yml` sidecar). A maintainer reviews and merges
— that review **is** the moderation step.

Nothing is written to the server's disk (Render's filesystem is ephemeral and data is read
once at startup). The PR is the write target, so the change flows through the existing,
proven pipeline: PR → `validate.yml` (landscape2 validate) → merge → `deploy.yml` rebuild.

---

## 1. How it works

```
Browser ── GET /admin/tools/new ─────────► HTML form (category/subcategory/project/tags/
        ── GET /admin/tools/{slug}/edit ──► NAF mapping pulled from settings.yml + data.yml)
        ── POST /admin/tools ────────────► 1. ToolForm (Pydantic) — enforces controlled vocab
                                            2. ruamel round-trip edit of data.yml (+ sidecar),
                                               preserving all comments & ordering
                                            3. jsonschema validate the WHOLE proposed data.yml
                                               against schemas/landscape2-data-schema.json
                                            4. open a GitHub PR to the FORK (or preview if no token)
                                            5. confirmation page with the PR link
```

Design decisions:

- **Write target = GitHub PR against the fork** (`cldeluna/network-automation-landscape`),
  never the upstream `steinzi/...` parent. See the fork-safety guard in §6.
- **Self-service + moderation** = anyone can submit; the maintainer's **merge** is the gate.
  No accounts; the server holds one bot token and opens PRs on submitters' behalf.
- **Pre-flight validation** closes the gap where `project`/`extra.tag` were free strings —
  the form now rejects bad values *before* a PR is opened, and runs the same JSON Schema CI
  uses, so a submission that would fail CI is blocked up front.

---

## 2. Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/tools/new` | Blank submission form |
| GET | `/admin/tools/{slug}/edit` | Form pre-filled from `data.yml` + sidecar |
| POST | `/admin/tools` | Validate → open PR (or render preview when no token) |

These render HTML (Jinja2). The existing read-only JSON API under `/api/v1/...` and the MCP
server at `/mcp` are unchanged.

---

## 3. Files in this branch

**New — admin layer (`api/admin/`):**
- `forms.py` — `ToolForm` / `ContactForm` Pydantic models. Enforces controlled vocabularies:
  `project` (14 maturity values), `extra.tag` (7 NAF components + `sdk`/`tool`/`lab`/`execution`),
  NAF components/sub-functions against `models.NAF_TAXONOMY`. `homepage_url` and `logo` are
  required (landscape2 mandates them). Projects the form to `to_data_item()` / `to_sidecar()`.
- `yaml_editor.py` — `ruamel.yaml` round-trip `upsert_item` / `upsert_sidecar`; preserves the
  ~2,300 lines of comments, ordering, and the `# yaml-language-server` hint.
- `schema_validate.py` — `jsonschema` validation of the full proposed `data.yml` against
  `schemas/landscape2-data-schema.json` (the same schema `landscape2 validate data` uses).
- `github_pr.py` — opens a PR via the GitHub REST API (branch → blobs → tree → commit → PR).
  Reads `GH_TOKEN` from env; graceful no-token degradation; **hard guard** against the
  upstream repo.

**New — router & templates:**
- `api/routers/admin.py` — the three routes; form parsing, placement/identity checks, PR vs.
  preview branching, submitter attribution in the PR body.
- `api/templates/{base,tool_form,submitted}.html` — server-rendered UI with dependent
  category→subcategory and NAF component→sub-function dropdowns (minimal inline JS).

**New — tests & docs:**
- `api/tests/test_admin.py` — 13 tests (round-trip, schema gate, vocab rejection, no-token
  preview, mocked PR path, upstream guard).
- `DATA_CRUD.md` — this file.

**Changed:**
- `pyproject.toml` — added `ruamel.yaml`, `jsonschema`, `jinja2`, `python-multipart`; promoted
  `httpx` from dev to runtime.
- `api/main.py` — mounts `admin.router`.

> Note: this branch also carries the earlier change that surfaces formal NAF mapping
> (`secondary_naf_components`) and records `collector` as SuzieQ's secondary component.

---

## 4. Controlled vocabulary enforced by the form

| Field | Allowed values |
|-------|----------------|
| `project` (maturity) | full-open-source, oss-with-paid-support, freemium, commercial-with-trial, commercial-only, enterprise, saas, hybrid, inactive, deprecated, end-of-life, archived, free-restrictive, closed-core |
| `extra.tag` | NAF: presentation, observability, orchestration, intent, collector, executor, network_infrastructure · plus: sdk, tool, lab, execution |
| `naf_component` / `secondary_naf_components` | the 7 NAF components |
| `naf_subfunctions` | must belong to the chosen `naf_component` (per `NAF_TAXONOMY`) |
| Required (schema) | `name`, `homepage_url`, `logo` |

---

## 5. Environment variables

| Var | Default | Purpose |
|-----|---------|---------|
| `GH_TOKEN` | _(unset)_ | GitHub token to open PRs. **Unset → preview mode** (renders the proposed diff instead of opening a PR). |
| `GH_REPO` | `cldeluna/network-automation-landscape` | Target repo (the fork). |
| `GH_BASE_BRANCH` | `main` | Branch the PR targets. |
| `SUBMIT_TOKEN` | _(unset)_ | Optional shared secret; when set, the form requires it (light anti-abuse). |
| `ALLOW_UPSTREAM_PR` | _(unset)_ | Safety override; must be set to ever target the upstream parent. Leave unset. |

**Never commit `GH_TOKEN` / `SUBMIT_TOKEN`.** Set them in the Render dashboard (§8).

### Creating a GitHub token (fine-grained PAT)
1. GitHub → Settings → Developer settings → **Fine-grained tokens** → Generate new token.
2. **Resource owner:** `cldeluna`. **Repository access:** only
   `cldeluna/network-automation-landscape`.
3. **Repository permissions:** **Contents: Read and write** + **Pull requests: Read and write**.
4. Copy the token into `GH_TOKEN` (locally for testing, or Render env for deploy).

---

## 6. Fork safety — PRs go to `cldeluna`, never upstream

`cldeluna/network-automation-landscape` is a **fork** of `steinzi/...`. GitHub's *web UI*
defaults a fork's new PR to the upstream parent — a common accidental-PR footgun. This code
avoids it two ways:

1. **By construction:** it POSTs to `/repos/cldeluna/.../pulls` with **both** `base: main`
   and `head: <branch>` inside `cldeluna` → an intra-fork PR that cannot land on upstream.
2. **By guard:** `open_pr` refuses to run if the target repo resolves to
   `steinzi/network-automation-landscape` unless `ALLOW_UPSTREAM_PR` is explicitly set.

Covered by `test_admin.py::test_upstream_pr_guard` and `::test_pr_path_mocked`
(asserts `cfg.repo == cldeluna/...`).

---

## 7. Testing locally

```bash
# 1. Install deps
uv sync

# 2. Run the unit tests (31 total: existing + 13 new admin tests)
uv run pytest api/tests/ -q

# 3. Run the app
uv run uvicorn api.main:app --reload
```

### A) Preview mode (no token — safe, opens nothing)
1. Open <http://127.0.0.1:8000/admin/tools/new>.
2. Fill the form (Name, Category→Subcategory, Homepage URL, Logo filename are required;
   pick a Maturity, tags, optionally NAF mapping + contacts; add your name/email).
3. Submit → the **confirmation page shows the exact `data.yml` diff** that *would* be proposed,
   with a "PR creation is not configured" notice. Nothing is sent to GitHub.
4. Try invalid input (e.g. an off-vocab tag, a subcategory from the wrong category, or omit the
   logo) → the form re-renders with a clear error. This proves the vocab/schema gate.

### B) Edit an existing tool
1. Open <http://127.0.0.1:8000/admin/tools/suzieq/edit> → the form is pre-filled, including
   `secondary_naf_components: [collector]` from the sidecar.
2. Change a field and submit → preview shows only that item's block changing.

### C) Live PR mode (real GitHub PR against the fork)
```bash
export GH_TOKEN=github_pat_xxx            # fine-grained PAT from §5
# optional: export SUBMIT_TOKEN=some-shared-secret
uv run uvicorn api.main:app --reload
```
Submit a tool → confirmation page links to a **real PR on `cldeluna/network-automation-landscape`**.
Verify the PR: it edits `data.yml` (+ `api/data/extended_data.yml` if you added contacts/NAF),
targets `main`, and the body attributes the submitter. `validate.yml` runs on it automatically.
Close the PR if it was just a test.

---

## 8. Testing on Render

The service is the existing `nal-api` Render web service (`render.yaml`), which serves REST +
MCP + (now) the admin form from one process.

1. **Deploy this branch.** Either point the service's branch at `feature/admin-crud-form`
   temporarily, or merge it up the chain (`feature/admin-crud-form` → `feature/mcp-server` →
   `main`) and let `autoDeploy` redeploy. The build (`uv sync --frozen`) picks up the new deps.
2. **Set env vars** in the Render dashboard → service → **Environment**:
   - `GH_TOKEN` = your fine-grained PAT (required for live PRs; omit to keep preview-only).
   - optionally `SUBMIT_TOKEN`, `GH_REPO`, `GH_BASE_BRANCH`.
   - Do **not** set `ALLOW_UPSTREAM_PR`.
3. **Exercise it:** visit `https://nal-api.onrender.com/admin/tools/new`. With no token it
   previews; with `GH_TOKEN` set it opens a PR on the fork.
4. **Reminders:**
   - Free tier spins down after ~15 min idle → first request is a ~30s cold start.
   - The API reads `data.yml` once at startup, so a merged PR won't show in `/api/v1/...` until
     the service redeploys (`autoDeploy` handles this on the next push to the deployed branch).
   - CORS is currently wide open (`*`) — lock down origins before treating this as more than a
     test deployment, since the form now performs writes (via PR).

---

## 9. Known limitations / future work

- **Logo upload** is not wired yet: the form takes a logo *filename* expected to already exist
  under `logos/`. Adding the binary to the same PR (multipart upload → git blob) is the planned
  next iteration; `python-multipart` is already installed and `github_pr.open_pr` accepts
  `binary_files`.
- **Anti-abuse** is light (required submitter email + optional `SUBMIT_TOKEN`). For a fully
  public deployment, add rate limiting / CAPTCHA.
- **Phase 2 (Dolt)** — a versioned SQL datastore with true CRUD/audit — remains the separate,
  larger path described in `CLAUDE.md`; this branch deliberately stays in the Git-PR model.

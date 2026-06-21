"""Tests for the self-service tool-submission form (admin layer).

Covers: round-trip YAML editing, pre-flight schema validation, controlled-vocab
rejection, the no-token preview path, and the PR path with GitHub calls mocked
(no real network). Also asserts the upstream-PR guard.
"""

import yaml

from api.admin import github_pr
from api.admin import yaml_editor as ye
from api.admin.forms import ToolForm
from api.admin.schema_validate import validate_landscape
from api.loader import DATA_YML, EXTENDED_DATA_YML

VALID = {
    "mode": "new",
    "name": "Acme Probe",
    "category": "Network state",
    "subcategory": "Network Source of Truth",
    "description": "A test probe.",
    "homepage_url": "https://acme.example",
    "logo": "acme.svg",
    "project": "full-open-source",
    "tags": ["intent", "collector"],
    "summary_use_case": "testing things",
    "naf_component": "intent",
    "naf_subfunctions": ["Intended State / SoT"],
    "secondary_naf_components": ["collector"],
    "submitter_name": "Tester",
    "submitter_email": "t@example.com",
}


# --- GET routes -------------------------------------------------------------


def test_new_form_renders(client):
    r = client.get("/admin/tools/new")
    assert r.status_code == 200
    assert "<form" in r.text
    assert "Network state" in r.text  # category options present


def test_edit_form_prefills(client):
    r = client.get("/admin/tools/suzieq/edit")
    assert r.status_code == 200
    assert "SuzieQ" in r.text
    assert "collector" in r.text  # secondary NAF from sidecar


def test_edit_unknown_404(client):
    assert client.get("/admin/tools/does-not-exist/edit").status_code == 404


# --- round-trip YAML editing ------------------------------------------------


def test_upsert_preserves_comments_and_validates():
    doc = ye.load_doc(DATA_YML.read_text())
    item = ToolForm(**VALID).to_data_item()
    action = ye.upsert_item(doc, VALID["category"], VALID["subcategory"], item)
    assert action == "created"
    out = ye.dump_doc(doc)
    # The schema hint comment at the top survives round-tripping.
    assert "yaml-language-server" in out
    # The proposed document passes the same schema CI uses.
    assert validate_landscape(yaml.safe_load(out)) == []


def test_upsert_edit_replaces_existing():
    doc = ye.load_doc(DATA_YML.read_text())
    item = {"name": "SuzieQ", "homepage_url": "https://x.example", "logo": "suzieq.png"}
    action = ye.upsert_item(doc, "Network state", "Testing, Compliance & Querying", item)
    assert action == "updated"


def test_sidecar_merge():
    doc = ye.load_doc(EXTENDED_DATA_YML.read_text())
    ye.upsert_sidecar(doc, "acme-probe", ToolForm(**VALID).to_sidecar())
    out = ye.dump_doc(doc)
    # Pre-existing entry is preserved alongside the new one.
    assert "suzieq" in out and "acme-probe" in out


# --- controlled-vocab validation -------------------------------------------


def test_bad_tag_rejected(client):
    bad = {**VALID, "tags": ["not-a-tag"]}
    r = client.post("/admin/tools", data=bad)
    assert r.status_code == 200
    assert "Unknown tag" in r.text
    assert "<form" in r.text  # back on the form


def test_missing_logo_rejected(client):
    bad = {k: v for k, v in VALID.items() if k != "logo"}
    r = client.post("/admin/tools", data=bad)
    assert r.status_code == 200
    assert "logo" in r.text.lower()


def test_bad_subcategory_rejected(client):
    bad = {**VALID, "subcategory": "Lab tools"}
    r = client.post("/admin/tools", data=bad)
    assert "is not in category" in r.text


def test_duplicate_in_new_mode_rejected(client):
    dup = {**VALID, "name": "SuzieQ", "subcategory": "Testing, Compliance & Querying"}
    r = client.post("/admin/tools", data=dup)
    assert "already exists" in r.text


# --- no-token preview path --------------------------------------------------


def test_preview_when_unconfigured(client, monkeypatch):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    r = client.post("/admin/tools", data=VALID)
    assert r.status_code == 200
    assert "Submission received" in r.text
    assert "not configured" in r.text
    assert "name: Acme Probe" in r.text  # diff preview


# --- PR path with GitHub mocked ---------------------------------------------


def test_pr_path_mocked(client, monkeypatch):
    captured = {}

    def fake_open_pr(cfg, *, branch, title, body, text_files, binary_files=None):
        captured["repo"] = cfg.repo
        captured["branch"] = branch
        captured["files"] = list(text_files)
        captured["body"] = body
        return {"html_url": "https://github.com/cldeluna/x/pull/42", "number": 42}

    monkeypatch.setenv("GH_TOKEN", "fake-token")
    monkeypatch.setattr(github_pr, "open_pr", fake_open_pr)

    r = client.post("/admin/tools", data=VALID)
    assert r.status_code == 200
    assert "Pull request opened" in r.text
    assert "pull/42" in r.text
    # PR targets the fork, includes both files, and attributes the submitter.
    assert captured["repo"] == "cldeluna/network-automation-landscape"
    assert "data.yml" in captured["files"]
    assert "api/data/extended_data.yml" in captured["files"]
    assert "Tester <t@example.com>" in captured["body"]
    assert captured["branch"].startswith("submit/acme-probe-")


# --- upstream guard ---------------------------------------------------------


def test_upstream_pr_guard(monkeypatch):
    monkeypatch.delenv("ALLOW_UPSTREAM_PR", raising=False)
    cfg = github_pr.GitHubConfig(
        token="t", repo=github_pr.UPSTREAM_REPO, base_branch="main"
    )
    try:
        github_pr.open_pr(
            cfg, branch="b", title="t", body="b", text_files={"data.yml": "x"}
        )
        raised = False
    except github_pr.GitHubError as exc:
        raised = "upstream" in str(exc).lower()
    assert raised

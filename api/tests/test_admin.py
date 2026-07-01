"""Tests for the self-service tool-submission form (admin layer).

Covers: round-trip YAML editing, pre-flight schema validation, controlled-vocab
rejection, the no-token preview path, and the PR path with GitHub calls mocked
(no real network). Also asserts the upstream-PR guard.
"""

import io

import yaml
from PIL import Image

from api.admin import github_pr, logo
from api.admin import yaml_editor as ye
from api.admin.forms import ToolForm
from api.admin.schema_validate import validate_landscape
from api.loader import DATA_YML, EXTENDED_DATA_YML


def _png_bytes(w=48, h=48) -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", (w, h), (0, 150, 255, 255)).save(buf, "PNG")
    return buf.getvalue()


EVIL_SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)" width="10" height="10">'
    b"<script>alert(document.cookie)</script>"
    b'<foreignObject><b>x</b></foreignObject>'
    b'<image href="https://evil.example/x.png"/>'
    b'<path d="M0 0 L5 5" fill="#09f"/></svg>'
)

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
        captured["binary"] = list(binary_files or {})
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


# --- logo handling ----------------------------------------------------------


def test_svg_sanitized():
    name, clean = logo.process_upload("acme-probe", "logo.svg", EVIL_SVG)
    text = clean.decode()
    assert name == "acme-probe.svg"
    assert "<script" not in text and "script>" not in text
    assert "onload" not in text
    assert "foreignobject" not in text.lower()
    assert "evil.example" not in text
    assert "M0 0 L5 5" in text  # legit path preserved


def test_svg_dtd_rejected():
    payload = b'<!DOCTYPE svg [<!ENTITY x "y">]><svg xmlns="http://www.w3.org/2000/svg"/>'
    try:
        logo.sanitize_svg(payload)
        raised = False
    except logo.LogoError:
        raised = True
    assert raised


def test_raster_validated_and_fake_rejected():
    name, clean = logo.process_upload("acme-probe", "logo.png", _png_bytes())
    assert name == "acme-probe.png" and len(clean) > 0
    try:
        logo.process_upload("x", "fake.png", b"not a png")
        raised = False
    except logo.LogoError:
        raised = True
    assert raised


def test_unsupported_logo_type_rejected():
    try:
        logo.process_upload("x", "evil.gif", b"GIF89a")
        raised = False
    except logo.LogoError:
        raised = True
    assert raised


def test_missing_logo_rejected_no_file(client):
    data = {k: v for k, v in VALID.items() if k != "logo"}
    r = client.post("/admin/tools", data=data)
    assert "logo is required" in r.text.lower()


def test_upload_commits_logo_binary(client, monkeypatch):
    captured = {}

    def fake_open_pr(cfg, *, branch, title, body, text_files, binary_files=None):
        captured["files"] = list(text_files)
        captured["binary"] = list(binary_files or {})
        return {"html_url": "https://github.com/cldeluna/x/pull/7", "number": 7}

    monkeypatch.setenv("GH_TOKEN", "fake-token")
    monkeypatch.setattr(github_pr, "open_pr", fake_open_pr)

    data = {k: v for k, v in VALID.items() if k != "logo"}  # no filename; use upload
    files = {"logo_file": ("logo.svg", EVIL_SVG, "image/svg+xml")}
    r = client.post("/admin/tools", data=data, files=files)
    assert r.status_code == 200
    assert "Pull request opened" in r.text
    # The sanitized logo is committed under logos/<slug>.svg.
    assert "logos/acme-probe.svg" in captured["binary"]


def test_logo_url_stored_in_sidecar():
    frag = ToolForm(**{**VALID, "logo_url": "https://cdn.example/acme.svg"}).to_sidecar()
    assert frag["logo_url"] == "https://cdn.example/acme.svg"
    doc = ye.load_doc(EXTENDED_DATA_YML.read_text())
    ye.upsert_sidecar(doc, "acme-probe", frag)
    out = ye.dump_doc(doc)
    assert "logo_urls" in out and "cdn.example" in out


def test_bad_logo_url_rejected(client):
    r = client.post("/admin/tools", data={**VALID, "logo_url": "ftp://nope"})
    assert "logo_url" in r.text


def test_tool_exposes_logo_url_field(client):
    # Field is present on the API surface (null for tools without one).
    r = client.get("/api/v1/tools/suzieq")
    assert r.status_code == 200
    assert "logo_url" in r.json()

def test_health(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_list_tools_non_empty(client):
    r = client.get("/api/v1/tools")
    assert r.status_code == 200
    tools = r.json()
    assert len(tools) > 0
    sample = tools[0]
    assert {"name", "slug", "category", "subcategory"}.issubset(sample.keys())


def test_get_tool_by_slug(client):
    r = client.get("/api/v1/tools")
    slug = r.json()[0]["slug"]
    r = client.get(f"/api/v1/tools/{slug}")
    assert r.status_code == 200
    assert r.json()["slug"] == slug


def test_get_tool_404(client):
    r = client.get("/api/v1/tools/does-not-exist")
    assert r.status_code == 404


def test_filter_tools_by_naf_component(client):
    r = client.get("/api/v1/tools", params={"naf_component": "intent"})
    assert r.status_code == 200
    tools = r.json()
    assert len(tools) > 0
    assert all("intent" in t["tags"] for t in tools)


def test_naf_taxonomy(client):
    r = client.get("/api/v1/naf")
    assert r.status_code == 200
    taxonomy = r.json()
    assert "intent" in taxonomy
    assert "executor" in taxonomy
    assert isinstance(taxonomy["intent"], list)


def test_naf_component_tools(client):
    r = client.get("/api/v1/naf/intent")
    assert r.status_code == 200
    assert len(r.json()) > 0


def test_naf_component_unknown_404(client):
    r = client.get("/api/v1/naf/not-a-component")
    assert r.status_code == 404


def test_use_cases_link_unconfigured(client):
    # Use cases live in an external system; with no base URL configured the
    # endpoint reports configured=false and a null link.
    r = client.get("/api/v1/use_cases")
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "external"
    assert body["configured"] is False
    assert body["use_cases_url"] is None


def test_tool_use_cases_link(client):
    r = client.get("/api/v1/tools")
    slug = r.json()[0]["slug"]
    r = client.get(f"/api/v1/tools/{slug}/use_cases")
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "external"
    assert "tool" in body


def test_tool_use_cases_link_404(client):
    r = client.get("/api/v1/tools/does-not-exist/use_cases")
    assert r.status_code == 404


def test_categories(client):
    r = client.get("/api/v1/categories")
    assert r.status_code == 200
    cats = r.json()
    assert len(cats) > 0
    assert all("name" in c and "subcategories" in c for c in cats)

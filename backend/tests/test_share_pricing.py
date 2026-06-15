"""New iteration: share/public/pricing/region tests."""
import os
import json
import time
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://aws-diagram-analyzer.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

SAMPLE_XML = """<mxGraphModel><root>
  <mxCell id="0"/><mxCell id="1" parent="0"/>
  <mxCell id="a" value="EC2" style="shape=mxgraph.aws4.ec2" vertex="1" parent="1">
    <mxGeometry x="0" y="0" width="80" height="80"/>
  </mxCell>
  <mxCell id="b" value="S3" style="shape=mxgraph.aws4.s3" vertex="1" parent="1">
    <mxGeometry x="120" y="0" width="80" height="80"/>
  </mxCell>
  <mxCell id="c" value="Lambda" style="shape=mxgraph.aws4.lambda" vertex="1" parent="1">
    <mxGeometry x="240" y="0" width="80" height="80"/>
  </mxCell>
</root></mxGraphModel>"""


@pytest.fixture(scope="module")
def s():
    return requests.Session()


@pytest.fixture(scope="module")
def headers(s):
    r = s.post(f"{API}/auth/login", json={"email": "test@architecht.dev", "password": "testpass123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


# ---------- Pricing ----------
class TestPricing:
    def test_pricing_us_east_1(self, s):
        r = s.get(f"{API}/pricing", params={"region": "us-east-1"})
        assert r.status_code == 200
        data = r.json()
        assert data["region"] == "us-east-1"
        assert len(data["items"]) >= 60  # ~69
        assert len(data["supported_regions"]) >= 15
        names = {i["name"]: i for i in data["items"]}
        assert "EC2" in names and "Lambda" in names and "S3" in names
        ec2 = names["EC2"]
        assert ec2["category"] == "compute"
        assert ec2["unit_cost_usd"] > 0
        assert "assumption" in ec2 and "source" in ec2 and "live_capable" in ec2

    def test_pricing_region_multiplier(self, s):
        # Compare us-east-1 vs ap-south-1 (multiplier 0.95)
        r1 = s.get(f"{API}/pricing", params={"region": "us-east-1"})
        r2 = s.get(f"{API}/pricing", params={"region": "ap-south-1"})
        assert r1.status_code == 200 and r2.status_code == 200
        n1 = {i["name"]: i for i in r1.json()["items"]}
        n2 = {i["name"]: i for i in r2.json()["items"]}
        # EC2 is curated (not live), so should reflect exact multiplier
        assert n1["EC2"]["unit_cost_usd"] == pytest.approx(30.37, abs=0.5)
        assert n2["EC2"]["unit_cost_usd"] == pytest.approx(30.37 * 0.95, abs=0.5)
        # eu-west-1 should be ~1.06x
        r3 = s.get(f"{API}/pricing", params={"region": "eu-west-1"})
        n3 = {i["name"]: i for i in r3.json()["items"]}
        assert n3["EC2"]["unit_cost_usd"] > n1["EC2"]["unit_cost_usd"]

    def test_pricing_refresh_requires_auth(self, s):
        r = s.post(f"{API}/pricing/refresh", params={"region": "us-east-1"})
        assert r.status_code == 401

    def test_pricing_refresh_lambda_at_least(self, s, headers):
        r = s.post(f"{API}/pricing/refresh", params={"region": "us-east-1"}, headers=headers, timeout=120)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["region"] == "us-east-1"
        assert "results" in data
        results = data["results"]
        # Lambda should always succeed per problem statement
        assert "Lambda" in results
        assert results["Lambda"].get("ok") is True, f"Lambda refresh failed: {results['Lambda']}"
        assert "monthly_cost_usd" in results["Lambda"]


# ---------- Share / Public ----------
@pytest.fixture(scope="module")
def created_lld(s, headers):
    """Generate a minimal LLD for share tests (uses real LLM)."""
    title = f"TEST_SHARE_{uuid.uuid4().hex[:6]}"
    payload = {"title": title, "xml": SAMPLE_XML, "region": "eu-west-1"}
    lld_id = None
    try:
        with requests.post(f"{API}/lld/generate", json=payload, headers=headers, stream=True, timeout=240) as r:
            assert r.status_code == 200, r.text
            start = time.time()
            for raw in r.iter_lines(decode_unicode=True):
                if raw and raw.startswith("data:"):
                    try:
                        ev = json.loads(raw[5:].strip())
                    except Exception:
                        continue
                    if ev.get("type") == "done":
                        lld_id = ev.get("lld_id")
                        break
                    if ev.get("type") == "error":
                        pytest.fail(f"gen error: {ev}")
                if time.time() - start > 200:
                    break
    except (requests.exceptions.ChunkedEncodingError, requests.exceptions.ConnectionError):
        pass

    if not lld_id:
        time.sleep(2.0)
        r = s.get(f"{API}/lld/find-by-title", params={"title": title}, headers=headers)
        if r.status_code == 200:
            lld_id = r.json()["id"]
    assert lld_id, "Could not obtain LLD id"
    return {"id": lld_id, "title": title}


class TestRegionLLD:
    def test_region_persisted_and_priced(self, s, headers, created_lld):
        r = s.get(f"{API}/lld/{created_lld['id']}", headers=headers)
        assert r.status_code == 200
        doc = r.json()
        assert doc["region"] == "eu-west-1"
        # EC2 cost should be > us-east-1 baseline (30.37) if present
        for svc in doc["services"]:
            if svc["name"] == "EC2":
                assert svc["unit_cost_usd"] > 30.37, f"eu-west-1 EC2 should be > us-east-1: {svc}"
                break

    def test_markdown_concise_and_has_sections(self, s, headers, created_lld):
        r = s.get(f"{API}/lld/{created_lld['id']}", headers=headers)
        doc = r.json()
        md = doc["markdown"]
        word_count = len(md.split())
        assert word_count < 3000, f"Markdown too long: {word_count} words"
        for section in ["Overview", "Components", "Data Flow", "Networking", "IAM", "Data Layer",
                         "CI/CD", "Observability", "Cost", "Recommendations"]:
            assert section.lower() in md.lower(), f"Missing section: {section}"


class TestShare:
    def test_share_creates_token(self, s, headers, created_lld):
        r = s.post(f"{API}/lld/{created_lld['id']}/share", headers=headers)
        assert r.status_code == 200
        body = r.json()
        assert body["is_public"] is True
        assert isinstance(body["share_token"], str) and len(body["share_token"]) > 10
        created_lld["token"] = body["share_token"]

    def test_share_idempotent(self, s, headers, created_lld):
        # Second call should return same token
        r1 = s.post(f"{API}/lld/{created_lld['id']}/share", headers=headers)
        r2 = s.post(f"{API}/lld/{created_lld['id']}/share", headers=headers)
        assert r1.json()["share_token"] == r2.json()["share_token"]

    def test_public_endpoint_no_auth(self, s, created_lld):
        token = created_lld["token"]
        # No auth header
        r = requests.get(f"{API}/public/lld/{token}")
        assert r.status_code == 200, r.text
        doc = r.json()
        assert doc["id"] == created_lld["id"]
        assert doc["title"] == created_lld["title"]
        assert "markdown" in doc and len(doc["markdown"]) > 50
        assert doc["region"] == "eu-west-1"
        assert "services" in doc and "pages" in doc
        # MUST NOT include user_id or xml
        assert "user_id" not in doc
        assert "xml" not in doc

    def test_public_accessible_by_other_user(self, s, created_lld):
        # Register another user
        email = f"other_{uuid.uuid4().hex[:8]}@architecht.dev"
        r = requests.post(f"{API}/auth/register", json={"email": email, "password": "pw123456", "name": "Other"})
        assert r.status_code == 200
        other_headers = {"Authorization": f"Bearer {r.json()['token']}"}
        # Public URL still works for them
        r2 = requests.get(f"{API}/public/lld/{created_lld['token']}", headers=other_headers)
        assert r2.status_code == 200

    def test_revoke_share(self, s, headers, created_lld):
        token = created_lld["token"]
        r = s.delete(f"{API}/lld/{created_lld['id']}/share", headers=headers)
        assert r.status_code == 200
        assert r.json()["is_public"] is False
        # Public URL should now 404
        r2 = requests.get(f"{API}/public/lld/{token}")
        assert r2.status_code == 404

    def test_public_invalid_token(self):
        r = requests.get(f"{API}/public/lld/nonexistent-token-xyz")
        assert r.status_code == 404


# ---------- Cleanup ----------
@pytest.fixture(scope="module", autouse=True)
def cleanup(s, headers, created_lld):
    yield
    try:
        requests.delete(f"{API}/lld/{created_lld['id']}", headers=headers, timeout=10)
    except Exception:
        pass

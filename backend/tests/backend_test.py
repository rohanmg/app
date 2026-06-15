"""Architecht backend integration tests.

Covers auth, drawio parse, LLD generate (SSE), CRUD, exports.
"""
import os
import json
import time
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://aws-diagram-analyzer.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

SAMPLE_XML = """<mxfile host="app.diagrams.net">
  <diagram name="Architecture">
    <mxGraphModel><root>
      <mxCell id="0"/>
      <mxCell id="1" parent="0"/>
      <mxCell id="ec2-1" value="Web EC2" style="shape=mxgraph.aws4.ec2;fillColor=#ED7100" vertex="1" parent="1">
        <mxGeometry x="40" y="40" width="80" height="80"/>
      </mxCell>
      <mxCell id="s3-1" value="App Bucket" style="shape=mxgraph.aws4.s3;fillColor=#7AA116" vertex="1" parent="1">
        <mxGeometry x="200" y="40" width="80" height="80"/>
      </mxCell>
      <mxCell id="rds-1" value="Primary DB" style="shape=mxgraph.aws4.rds" vertex="1" parent="1">
        <mxGeometry x="360" y="40" width="80" height="80"/>
      </mxCell>
      <mxCell id="lam-1" value="Worker" style="shape=mxgraph.aws4.lambda" vertex="1" parent="1">
        <mxGeometry x="520" y="40" width="80" height="80"/>
      </mxCell>
      <mxCell id="e1" edge="1" source="ec2-1" target="s3-1" parent="1"/>
      <mxCell id="e2" edge="1" source="ec2-1" target="rds-1" parent="1"/>
    </root></mxGraphModel>
  </diagram>
  <diagram name="DataPlane">
    <mxGraphModel><root>
      <mxCell id="0"/>
      <mxCell id="1" parent="0"/>
      <mxCell id="dy-1" value="Sessions" style="shape=mxgraph.aws4.dynamodb" vertex="1" parent="1">
        <mxGeometry x="40" y="40" width="80" height="80"/>
      </mxCell>
    </root></mxGraphModel>
  </diagram>
</mxfile>"""

SIMPLE_XML = """<mxGraphModel><root>
  <mxCell id="0"/><mxCell id="1" parent="0"/>
  <mxCell id="a" value="EC2" style="shape=mxgraph.aws4.ec2" vertex="1" parent="1">
    <mxGeometry x="0" y="0" width="80" height="80"/>
  </mxCell>
</root></mxGraphModel>"""


@pytest.fixture(scope="module")
def s():
    return requests.Session()


@pytest.fixture(scope="module")
def primary_user(s):
    """Use existing test user; login first, fallback register."""
    email = "test@architecht.dev"
    password = "testpass123"
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password})
    if r.status_code != 200:
        r = s.post(f"{API}/auth/register", json={"email": email, "password": password, "name": "Test User"})
    assert r.status_code in (200, 201), r.text
    return r.json()


@pytest.fixture(scope="module")
def token(primary_user):
    return primary_user["token"]


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}"}


# ---------- Health ----------
def test_health():
    r = requests.get(f"{API}/")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


# ---------- Auth ----------
class TestAuth:
    def test_register_duplicate(self, s):
        email = f"dup_{uuid.uuid4().hex[:8]}@architecht.dev"
        r1 = s.post(f"{API}/auth/register", json={"email": email, "password": "pw123456", "name": "Dup User"})
        assert r1.status_code == 200, r1.text
        body = r1.json()
        assert "token" in body and body["user"]["email"] == email
        r2 = s.post(f"{API}/auth/register", json={"email": email, "password": "pw123456", "name": "Dup User"})
        assert r2.status_code == 409

    def test_login_invalid(self, s):
        r = s.post(f"{API}/auth/login", json={"email": "test@architecht.dev", "password": "wrong-pw"})
        assert r.status_code == 401

    def test_login_valid_and_me(self, s, primary_user, headers):
        assert "token" in primary_user
        r = s.get(f"{API}/auth/me", headers=headers)
        assert r.status_code == 200
        assert r.json()["email"] == "test@architecht.dev"

    def test_me_without_token(self, s):
        r = s.get(f"{API}/auth/me")
        assert r.status_code == 401


# ---------- Drawio parse ----------
class TestDrawio:
    def test_parse_multipage(self, s, headers):
        r = s.post(f"{API}/drawio/parse", json={"xml": SAMPLE_XML}, headers=headers)
        assert r.status_code == 200, r.text
        data = r.json()
        assert len(data["pages"]) == 2
        sc = data["service_counts"]
        for svc in ["EC2", "S3", "RDS", "Lambda", "DynamoDB"]:
            assert svc in sc, f"Missing {svc} in {sc}"
        assert data["estimated_monthly_cost_usd"] > 0
        assert any(c["name"] == "EC2" for c in data["cost_breakdown"])

    def test_parse_simple_mxgraph(self, s, headers):
        r = s.post(f"{API}/drawio/parse", json={"xml": SIMPLE_XML}, headers=headers)
        assert r.status_code == 200
        d = r.json()
        assert d["service_counts"].get("EC2") == 1

    def test_parse_invalid(self, s, headers):
        r = s.post(f"{API}/drawio/parse", json={"xml": "<not-xml<<<"}, headers=headers)
        assert r.status_code == 400

    def test_parse_unauthorized(self, s):
        r = s.post(f"{API}/drawio/parse", json={"xml": SIMPLE_XML})
        assert r.status_code == 401


# ---------- LLD generation (SSE) ----------
@pytest.fixture(scope="module")
def generated_lld(s, headers):
    """Run real LLM streaming and persist - shared across tests.
    If preview ingress cuts the SSE stream before 'done', recover via find-by-title
    (backend persists in asyncio.shield on CancelledError).
    """
    url = f"{API}/lld/generate"
    title = f"TEST_Architecht_LLD_{uuid.uuid4().hex[:6]}"
    payload = {"title": title, "xml": SAMPLE_XML}
    events = []
    lld_id = None
    saw_meta = False
    delta_count = 0
    error_msg = None

    try:
        with requests.post(url, json=payload, headers=headers, stream=True, timeout=240) as r:
            assert r.status_code == 200, r.text
            start = time.time()
            for raw in r.iter_lines(decode_unicode=True):
                if raw is None:
                    continue
                if not raw or not raw.startswith("data:"):
                    continue
                try:
                    ev = json.loads(raw[5:].strip())
                except Exception:
                    continue
                events.append(ev)
                t = ev.get("type")
                if t == "meta":
                    saw_meta = True
                    assert events[0]["type"] == "meta", "meta must come first"
                elif t == "delta":
                    delta_count += 1
                elif t == "error":
                    error_msg = ev.get("message")
                    break
                elif t == "done":
                    lld_id = ev.get("lld_id")
                    break
                if time.time() - start > 200:
                    pytest.fail("SSE stream exceeded 200s")
    except (requests.exceptions.ChunkedEncodingError, requests.exceptions.ConnectionError):
        # Ingress cut the stream — backend should still have persisted via shield
        pass

    # Recovery: if no 'done' event seen, wait briefly then query find-by-title
    if not lld_id and not error_msg:
        time.sleep(2.0)
        r = s.get(f"{API}/lld/find-by-title", params={"title": title}, headers=headers)
        if r.status_code == 200:
            lld_id = r.json()["id"]

    return {"lld_id": lld_id, "events": events, "saw_meta": saw_meta, "delta_count": delta_count, "error": error_msg, "title": title}


class TestLLDGenerate:
    def test_stream_completes(self, generated_lld):
        assert generated_lld["error"] is None, f"Stream error: {generated_lld['error']}"
        assert generated_lld["saw_meta"] is True
        assert generated_lld["delta_count"] > 0, "Expected at least one delta from LLM"
        # lld_id may come from 'done' event or recovery via find-by-title (both validate
        # backend persistence via asyncio.shield on CancelledError)
        assert generated_lld["lld_id"], "Expected lld_id (via done event or find-by-title recovery)"

    def test_meta_payload(self, generated_lld):
        meta = generated_lld["events"][0]
        assert "pages" in meta and "service_counts" in meta and "cost_breakdown" in meta
        assert meta["estimated_monthly_cost_usd"] > 0


# ---------- LLD CRUD + exports ----------
class TestLLDCrud:
    def test_list(self, s, headers, generated_lld):
        r = s.get(f"{API}/lld", headers=headers)
        assert r.status_code == 200
        items = r.json()
        assert any(it["id"] == generated_lld["lld_id"] for it in items)

    def test_get(self, s, headers, generated_lld):
        r = s.get(f"{API}/lld/{generated_lld['lld_id']}", headers=headers)
        assert r.status_code == 200
        doc = r.json()
        assert doc["title"] == generated_lld["title"]
        assert len(doc["markdown"]) > 100
        assert doc["estimated_monthly_cost_usd"] > 0
        assert len(doc["pages"]) == 2

    def test_export_markdown(self, s, headers, generated_lld):
        r = s.get(f"{API}/lld/{generated_lld['lld_id']}/export/markdown", headers=headers)
        assert r.status_code == 200
        assert "markdown" in r.headers.get("content-type", "")
        assert "attachment" in r.headers.get("content-disposition", "")
        assert len(r.content) > 50

    def test_export_docx(self, s, headers, generated_lld):
        r = s.get(f"{API}/lld/{generated_lld['lld_id']}/export/docx", headers=headers)
        assert r.status_code == 200
        assert r.content[:2] == b"PK"  # docx is a zip
        assert "attachment" in r.headers.get("content-disposition", "")

    def test_other_user_cannot_access(self, s, generated_lld):
        # Register a second user
        email = f"other_{uuid.uuid4().hex[:8]}@architecht.dev"
        r = s.post(f"{API}/auth/register", json={"email": email, "password": "pw123456", "name": "Other"})
        assert r.status_code == 200
        other_headers = {"Authorization": f"Bearer {r.json()['token']}"}
        # Get other's LLD should 404
        r2 = s.get(f"{API}/lld/{generated_lld['lld_id']}", headers=other_headers)
        assert r2.status_code == 404
        # Delete should 404
        r3 = s.delete(f"{API}/lld/{generated_lld['lld_id']}", headers=other_headers)
        assert r3.status_code == 404

    def test_find_by_title_success(self, s, headers, generated_lld):
        r = s.get(f"{API}/lld/find-by-title", params={"title": generated_lld["title"]}, headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["id"] == generated_lld["lld_id"]
        assert "created_at" in body

    def test_find_by_title_404(self, s, headers):
        r = s.get(f"{API}/lld/find-by-title", params={"title": "TEST_does_not_exist_xyz"}, headers=headers)
        assert r.status_code == 404

    def test_find_by_title_user_isolation(self, s, generated_lld):
        email = f"iso_{uuid.uuid4().hex[:8]}@architecht.dev"
        r = s.post(f"{API}/auth/register", json={"email": email, "password": "pw123456", "name": "Iso"})
        assert r.status_code == 200
        other_headers = {"Authorization": f"Bearer {r.json()['token']}"}
        # Other user should NOT find the primary user's LLD by title
        r2 = s.get(f"{API}/lld/find-by-title", params={"title": generated_lld["title"]}, headers=other_headers)
        assert r2.status_code == 404

    def test_delete(self, s, headers, generated_lld):
        r = s.delete(f"{API}/lld/{generated_lld['lld_id']}", headers=headers)
        assert r.status_code == 200
        r2 = s.get(f"{API}/lld/{generated_lld['lld_id']}", headers=headers)
        assert r2.status_code == 404

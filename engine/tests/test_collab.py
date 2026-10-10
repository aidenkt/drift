import pytest
from fastapi.testclient import TestClient

import collab
from app import app

OWNER = {"X-Dev-User": "owner@firm.com", "X-Dev-Name": "Olive Owner"}
EDITOR = {"X-Dev-User": "ed@firm.com"}
STRANGER = {"X-Dev-User": "nobody@else.com"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(collab, "DOCS", tmp_path)
    monkeypatch.setattr(collab, "INDEX", tmp_path / "index.json")
    monkeypatch.setenv("SINCE_DEV_AUTH", "1")
    return TestClient(app)


def create(client):
    r = client.post("/workbooks", files={"file": ("plan.xlsx", b"xlsx-bytes")}, headers=OWNER)
    assert r.status_code == 200
    return r.json()["doc_id"]


def test_only_people_it_is_shared_with_can_see_a_doc(client):
    doc = create(client)
    assert [d["doc_id"] for d in client.get("/workbooks", headers=OWNER).json()] == [doc]
    assert client.get("/workbooks", headers=STRANGER).json() == []
    assert client.get(f"/workbooks/{doc}/file", headers=STRANGER).status_code == 404

    r = client.put(f"/workbooks/{doc}/members", json={"email": "Ed@Firm.com", "role": "editor"}, headers=OWNER)
    assert r.json()["members"] == [{"email": "ed@firm.com", "role": "editor"}]
    shared = client.get("/workbooks", headers=EDITOR).json()
    assert shared[0]["role"] == "editor" and shared[0]["owner"]["name"] == "Olive Owner"
    assert client.get(f"/workbooks/{doc}/file", headers=EDITOR).content == b"xlsx-bytes"

    client.delete(f"/workbooks/{doc}/members/ed@firm.com", headers=OWNER)
    assert client.get("/workbooks", headers=EDITOR).json() == []


def test_roles(client):
    doc = create(client)
    client.put(f"/workbooks/{doc}/members", json={"email": "ed@firm.com", "role": "viewer"}, headers=OWNER)
    save = lambda h: client.put(f"/workbooks/{doc}/file", files={"file": ("plan.xlsx", b"v2")}, headers=h)
    assert save(EDITOR).status_code == 403  # viewers can't save
    assert client.put(f"/workbooks/{doc}/members", json={"email": "x@y.com"}, headers=EDITOR).status_code == 403

    client.put(f"/workbooks/{doc}/members", json={"email": "ed@firm.com", "role": "editor"}, headers=OWNER)
    assert save(EDITOR).status_code == 200
    assert client.get(f"/workbooks/{doc}", headers=OWNER).json()["updated_by"] == "ed@firm.com"


def test_rejects_bad_shares(client):
    doc = create(client)
    bad = lambda body: client.put(f"/workbooks/{doc}/members", json=body, headers=OWNER).status_code
    assert bad({"email": "not-an-email"}) == 422
    assert bad({"email": "a@b.com", "role": "admin"}) == 422
    assert bad({"email": "owner@firm.com"}) == 422


def test_needs_identity(client, monkeypatch):
    monkeypatch.delenv("SINCE_DEV_AUTH")
    monkeypatch.setenv("CLERK_ISSUER", "https://example.clerk.accounts.dev")
    assert client.get("/workbooks", headers=OWNER).status_code == 401


def test_presence_lists_who_is_here_and_their_cell(client):
    doc = create(client)
    client.put(f"/workbooks/{doc}/members", json={"email": "ed@firm.com"}, headers=OWNER)
    with client.websocket_connect(f"/workbooks/{doc}/presence?dev=owner@firm.com&name=Olive") as a:
        assert [p["email"] for p in a.receive_json()["people"]] == ["owner@firm.com"]
        with client.websocket_connect(f"/workbooks/{doc}/presence?dev=ed@firm.com") as b:
            assert len(a.receive_json()["people"]) == 2
            assert len(b.receive_json()["people"]) == 2
            b.send_json({"type": "cell", "cell": "Assumptions!B20"})
            people = {p["email"]: p for p in a.receive_json()["people"]}
            assert people["ed@firm.com"]["cell"] == "Assumptions!B20"
        assert [p["email"] for p in a.receive_json()["people"]] == ["owner@firm.com"]


def test_presence_refuses_people_without_access(client):
    doc = create(client)
    with client.websocket_connect(f"/workbooks/{doc}/presence?dev=nobody@else.com") as ws:
        with pytest.raises(Exception):
            ws.receive_json()

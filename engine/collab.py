"""Shared documents: who owns a workbook, who it's shared with, and who has it open right now.

Identity comes from Clerk. The browser sends its Clerk session token; we verify it against the
instance's public keys and look up the user's email (CLERK_SECRET_KEY) or read an `email`
claim added in Clerk's session token settings. With no Clerk configured (local dev) the
browser's X-Dev-User email is trusted instead (also when SINCE_DEV_AUTH=1).

Workbooks and the access index live under engine/uploads/docs, so they survive restarts.
Presence is in memory: one set of WebSocket connections per document.
"""

import asyncio
import base64
import json
import os
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import httpx
import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel

DOCS = Path(__file__).parent / "uploads" / "docs"
INDEX = DOCS / "index.json"
ROLES = ("editor", "viewer")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

router = APIRouter(prefix="/workbooks")  # not /docs: FastAPI serves its API docs there


# ---------- identity ----------


@dataclass(frozen=True)
class User:
    email: str
    name: str


def _clerk_issuer() -> str | None:
    """https://<frontend api> from CLERK_ISSUER, or decoded from the publishable key."""
    if issuer := os.getenv("CLERK_ISSUER"):
        return issuer.rstrip("/")
    key = os.getenv("CLERK_PUBLISHABLE_KEY") or os.getenv("VITE_CLERK_PUBLISHABLE_KEY")
    if not key or "_" not in key:
        return None
    encoded = key.split("_", 2)[-1]
    host = base64.b64decode(encoded + "=" * (-len(encoded) % 4)).decode().rstrip("$")
    return f"https://{host}"


_jwks: jwt.PyJWKClient | None = None
_emails: dict[str, User] = {}  # Clerk user id -> user, so we ask Clerk once per person


async def _clerk_user(token: str) -> User:
    global _jwks
    issuer = _clerk_issuer()
    if _jwks is None:
        _jwks = jwt.PyJWKClient(f"{issuer}/.well-known/jwks.json")
    try:
        key = await asyncio.to_thread(_jwks.get_signing_key_from_jwt, token)
        claims = jwt.decode(token, key.key, algorithms=["RS256"], issuer=issuer, leeway=10)
    except jwt.PyJWTError as e:
        raise HTTPException(401, f"Invalid session: {e}") from e

    sub = claims["sub"]
    if claims.get("email"):
        return User(claims["email"].lower(), claims.get("name") or claims["email"])
    if sub in _emails:
        return _emails[sub]
    secret = os.getenv("CLERK_SECRET_KEY")
    if not secret:
        raise HTTPException(
            401,
            "Can't tell who you are: set CLERK_SECRET_KEY in .env, or add an `email` claim to Clerk's session token.",
        )
    async with httpx.AsyncClient(timeout=10) as http:
        r = await http.get(f"https://api.clerk.com/v1/users/{sub}", headers={"Authorization": f"Bearer {secret}"})
    if r.status_code != 200:
        raise HTTPException(401, "Couldn't look up your Clerk account")
    u = r.json()
    primary = next(
        (e["email_address"] for e in u["email_addresses"] if e["id"] == u.get("primary_email_address_id")),
        u["email_addresses"][0]["email_address"],
    )
    name = " ".join(filter(None, [u.get("first_name"), u.get("last_name")])) or primary
    _emails[sub] = User(primary.lower(), name)
    return _emails[sub]


async def identify(token: str | None, dev_user: str | None, dev_name: str | None = None) -> User:
    if token:
        return await _clerk_user(token)
    # local dev only: no Clerk configured, or SINCE_DEV_AUTH=1 to test with several guest tabs
    if dev_user and (_clerk_issuer() is None or os.getenv("SINCE_DEV_AUTH") == "1"):
        return User(dev_user.lower(), dev_name or dev_user)
    raise HTTPException(401, "Sign in to share")


async def current_user(
    authorization: str | None = Header(None),
    x_dev_user: str | None = Header(None),
    x_dev_name: str | None = Header(None),
) -> User:
    token = authorization.removeprefix("Bearer ").strip() if authorization else None
    return await identify(token, x_dev_user, x_dev_name)


# ---------- documents and access ----------


def _load() -> dict[str, dict]:
    return json.loads(INDEX.read_text()) if INDEX.exists() else {}


def _save(docs: dict[str, dict]) -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    tmp = INDEX.with_suffix(".tmp")
    tmp.write_text(json.dumps(docs, indent=2))
    tmp.replace(INDEX)


def _role(doc: dict, user: User) -> str | None:
    if doc["owner"]["email"] == user.email:
        return "owner"
    return doc["members"].get(user.email)


def _get(doc_id: str, user: User, need: tuple[str, ...] = ("owner", "editor", "viewer")) -> tuple[dict, dict, str]:
    docs = _load()
    doc = docs.get(doc_id)
    role = _role(doc, user) if doc else None
    if not doc or role is None:
        raise HTTPException(404, "No such document, or it isn't shared with you")
    if role not in need:
        raise HTTPException(403, f"Needs {' or '.join(need)} access")
    return docs, doc, role


def _public(doc: dict, role: str) -> dict:
    return {
        "doc_id": doc["id"],
        "filename": doc["filename"],
        "owner": doc["owner"],
        "members": [{"email": e, "role": r} for e, r in doc["members"].items()],
        "role": role,
        "updated": doc["updated"],
        "updated_by": doc.get("updated_by"),
    }


@router.get("")
def list_docs(user: User = Depends(current_user)):
    out = [_public(d, r) for d in _load().values() if (r := _role(d, user))]
    return sorted(out, key=lambda d: d["updated"], reverse=True)


@router.post("")
async def create_doc(file: UploadFile, user: User = Depends(current_user)):
    doc_id = uuid.uuid4().hex[:10]
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / f"{doc_id}.xlsx").write_bytes(await file.read())
    now = time.time()
    docs = _load()
    docs[doc_id] = {
        "id": doc_id,
        "filename": file.filename or "model.xlsx",
        "owner": {"email": user.email, "name": user.name},
        "members": {},
        "updated": now,
        "updated_by": user.email,
    }
    _save(docs)
    return _public(docs[doc_id], "owner")


@router.get("/{doc_id}")
def get_doc(doc_id: str, user: User = Depends(current_user)):
    _, doc, role = _get(doc_id, user)
    return _public(doc, role)


@router.get("/{doc_id}/file")
def get_file(doc_id: str, user: User = Depends(current_user)):
    _, doc, _ = _get(doc_id, user)
    return FileResponse(DOCS / f"{doc_id}.xlsx", filename=doc["filename"])


@router.put("/{doc_id}/file")
async def save_file(doc_id: str, file: UploadFile, user: User = Depends(current_user)):
    docs, doc, _ = _get(doc_id, user, ("owner", "editor"))
    (DOCS / f"{doc_id}.xlsx").write_bytes(await file.read())
    doc["updated"], doc["updated_by"] = time.time(), user.email
    _save(docs)
    await presence.broadcast(doc_id, {"type": "saved", "by": user.email, "name": user.name, "at": doc["updated"]})
    return {"updated": doc["updated"]}


class Member(BaseModel):
    email: str
    role: str = "editor"


@router.put("/{doc_id}/members")
def share(doc_id: str, m: Member, user: User = Depends(current_user)):
    docs, doc, _ = _get(doc_id, user, ("owner",))
    email = m.email.strip().lower()
    if not EMAIL.match(email):
        raise HTTPException(422, f"{m.email} isn't an email address")
    if m.role not in ROLES:
        raise HTTPException(422, f"Role must be one of {', '.join(ROLES)}")
    if email == doc["owner"]["email"]:
        raise HTTPException(422, "That's the owner")
    doc["members"][email] = m.role
    _save(docs)
    return _public(doc, "owner")


@router.delete("/{doc_id}/members/{email}")
def unshare(doc_id: str, email: str, user: User = Depends(current_user)):
    docs, doc, _ = _get(doc_id, user, ("owner",))
    doc["members"].pop(email.lower(), None)
    _save(docs)
    return _public(doc, "owner")


# ---------- presence ----------


class Presence:
    """Who has each document open, and which cell they're on."""

    def __init__(self):
        self.rooms: dict[str, dict[WebSocket, dict]] = {}

    def people(self, doc_id: str) -> list[dict]:
        # one entry per person, even with the doc open in several tabs; latest cell wins
        seen: dict[str, dict] = {}
        for info in self.rooms.get(doc_id, {}).values():
            seen[info["email"]] = info
        return list(seen.values())

    async def broadcast(self, doc_id: str, message: dict):
        for ws in list(self.rooms.get(doc_id, {})):
            try:
                await ws.send_json(message)
            except Exception:
                self.rooms[doc_id].pop(ws, None)

    async def announce(self, doc_id: str):
        await self.broadcast(doc_id, {"type": "presence", "people": self.people(doc_id)})


presence = Presence()


@router.websocket("/{doc_id}/presence")
async def presence_socket(
    ws: WebSocket,
    doc_id: str,
    token: str | None = Query(None),
    dev: str | None = Query(None),
    name: str | None = Query(None),
):
    await ws.accept()
    try:
        user = await identify(token, dev, name)
        _, _, role = _get(doc_id, user)
    except HTTPException as e:
        await ws.close(code=4401 if e.status_code == 401 else 4403, reason=str(e.detail)[:120])
        return

    room = presence.rooms.setdefault(doc_id, {})
    room[ws] = {"email": user.email, "name": user.name, "role": role, "cell": None}
    await presence.announce(doc_id)
    try:
        while True:
            msg = await ws.receive_json()
            if msg.get("type") == "cell":
                room[ws]["cell"] = msg.get("cell")
                await presence.announce(doc_id)
    except WebSocketDisconnect:
        pass
    finally:
        room.pop(ws, None)
        if not room:
            presence.rooms.pop(doc_id, None)
        else:
            await presence.announce(doc_id)

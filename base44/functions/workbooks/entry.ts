// Shared workbooks: who owns one, who it's shared with, and the file itself.
//
// Callers sign in with Clerk, not Base44, so every request carries the Clerk session token and
// this function verifies it against the Clerk instance's public keys. The email comes from an
// `email` claim (Clerk session token customization) or from Clerk's API with CLERK_SECRET_KEY.
//
// Workbook is an admin-only entity and each file is a private upload; this function reaches both
// as service role after checking access, so it is the only way in.
import { createClientFromRequest } from "npm:@base44/sdk";
import { secrets } from "base44:runtime";
import { createRemoteJWKSet, jwtVerify } from "npm:jose@5";

type Role = "owner" | "editor" | "viewer";
type User = { email: string; name: string };
type Member = { email: string; role: "editor" | "viewer" };
type Workbook = {
  id: string;
  filename: string;
  owner_email: string;
  owner_name?: string;
  members: Member[];
  member_emails: string[];
  updated: number;
  updated_by?: string;
  file_uri: string; // private upload: read through a short-lived signed URL
};

class Fail extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

/* ---------- identity ---------- */

const secret = async (name: string) => ((await secrets.get(name)) as string | undefined) || undefined;

async function issuer(): Promise<string | null> {
  const explicit = await secret("CLERK_ISSUER");
  if (explicit) return explicit.replace(/\/$/, "");
  const key = await secret("CLERK_PUBLISHABLE_KEY");
  if (!key || !key.includes("_")) return null;
  const encoded = key.split("_").slice(2).join("_");
  return `https://${atob(encoded.padEnd(encoded.length + ((4 - (encoded.length % 4)) % 4), "=")).replace(/\$$/, "")}`;
}

let jwks: { iss: string; set: ReturnType<typeof createRemoteJWKSet> } | null = null;
const emails = new Map<string, User>(); // Clerk user id -> user, for this instance's lifetime

async function clerkUser(token: string): Promise<User> {
  const iss = await issuer();
  if (!iss) throw new Fail(500, "Clerk isn't configured: set CLERK_PUBLISHABLE_KEY or CLERK_ISSUER");
  if (jwks?.iss !== iss) jwks = { iss, set: createRemoteJWKSet(new URL(`${iss}/.well-known/jwks.json`)) };
  let claims: Record<string, unknown>;
  try {
    ({ payload: claims } = await jwtVerify(token, jwks.set, { issuer: iss, clockTolerance: 10 }));
  } catch (e) {
    throw new Fail(401, `Invalid session: ${(e as Error).message}`);
  }
  const sub = String(claims.sub);
  if (typeof claims.email === "string") return { email: claims.email.toLowerCase(), name: String(claims.name ?? claims.email) };
  const cached = emails.get(sub);
  if (cached) return cached;

  const key = await secret("CLERK_SECRET_KEY");
  if (!key) throw new Fail(401, "Can't tell who you are: set CLERK_SECRET_KEY, or add an `email` claim to Clerk's session token.");
  const r = await fetch(`https://api.clerk.com/v1/users/${sub}`, { headers: { Authorization: `Bearer ${key}` } });
  if (!r.ok) throw new Fail(401, "Couldn't look up your Clerk account");
  const u = await r.json();
  const primary: string =
    u.email_addresses.find((e: { id: string }) => e.id === u.primary_email_address_id)?.email_address ?? u.email_addresses[0].email_address;
  const user = { email: primary.toLowerCase(), name: [u.first_name, u.last_name].filter(Boolean).join(" ") || primary };
  emails.set(sub, user);
  return user;
}

async function identify(body: { token?: string }): Promise<User> {
  if (body.token) return clerkUser(body.token);
  throw new Fail(401, "Sign in to share");
}

/* ---------- access ---------- */

const roleOf = (w: Workbook, u: User): Role | null =>
  w.owner_email === u.email ? "owner" : (w.members.find((m) => m.email === u.email)?.role ?? null);

const view = (w: Workbook, role: Role) => ({
  doc_id: w.id,
  filename: w.filename,
  owner: { email: w.owner_email, name: w.owner_name ?? w.owner_email },
  members: w.members,
  role,
  updated: w.updated,
  updated_by: w.updated_by ?? null,
});

const now = () => Date.now() / 1000;

// files travel to and from the browser as base64
const toBytes = (b64: string) => Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
function toBase64(bytes: Uint8Array): string {
  let s = "";
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(s);
}

export default async function handler(req: Request): Promise<Response> {
  try {
    const body = await req.json();
    const base44 = createClientFromRequest(req);
    const db = base44.asServiceRole.entities;
    const user = await identify(body);

    // the workbook, if the caller has one of the roles in `need`
    const load = async (need: Role[] = ["owner", "editor", "viewer"]) => {
      const w = (await db.Workbook.get(String(body.id)).catch(() => null)) as Workbook | null;
      const role = w ? roleOf(w, user) : null;
      if (!w || !role) throw new Fail(404, "No such workbook, or it isn't shared with you");
      if (!need.includes(role)) throw new Fail(403, `Needs ${need.join(" or ")} access`);
      return { w, role };
    };
    const core = base44.asServiceRole.integrations.Core;
    const upload = async (b64: string, filename: string) => {
      if (typeof b64 !== "string" || !b64) throw new Fail(422, "No file");
      const file = new File([toBytes(b64)], filename, { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
      return ((await core.UploadPrivateFile({ file })) as { file_uri: string }).file_uri;
    };

    switch (body.action) {
      case "list": {
        const rows = (await db.Workbook.filter({ $or: [{ owner_email: user.email }, { member_emails: user.email }] })) as Workbook[];
        return Response.json(rows.map((w) => view(w, roleOf(w, user)!)).sort((a, b) => b.updated - a.updated));
      }
      case "create": {
        const filename = String(body.filename || "model.xlsx");
        const file_uri = await upload(body.data, filename);
        const w = (await db.Workbook.create({
          filename,
          file_uri,
          owner_email: user.email,
          owner_name: user.name,
          members: [],
          member_emails: [],
          updated: now(),
          updated_by: user.email,
        })) as Workbook;
        return Response.json(view(w, "owner"));
      }
      case "get": {
        const { w, role } = await load();
        return Response.json(view(w, role));
      }
      case "file": {
        const { w } = await load();
        const { signed_url } = (await core.CreateFileSignedUrl({ file_uri: w.file_uri, expires_in: 60 })) as { signed_url: string };
        const r = await fetch(signed_url);
        if (!r.ok) throw new Fail(502, "Couldn't read the stored file");
        return Response.json({ data: toBase64(new Uint8Array(await r.arrayBuffer())), filename: w.filename });
      }
      case "save": {
        const { w } = await load(["owner", "editor"]);
        const file_uri = await upload(body.data, w.filename);
        const updated = now();
        await db.Workbook.update(w.id, { file_uri, updated, updated_by: user.email });
        return Response.json({ updated });
      }
      case "share": {
        const { w } = await load(["owner"]);
        const email = String(body.email ?? "").trim().toLowerCase();
        const role = body.role ?? "editor";
        if (!EMAIL.test(email)) throw new Fail(422, `${body.email} isn't an email address`);
        if (role !== "editor" && role !== "viewer") throw new Fail(422, "Role must be editor or viewer");
        if (email === w.owner_email) throw new Fail(422, "That's the owner");
        const members = [...w.members.filter((m) => m.email !== email), { email, role }];
        const next = { ...w, members, member_emails: members.map((m) => m.email) };
        await db.Workbook.update(w.id, { members: next.members, member_emails: next.member_emails });
        return Response.json(view(next, "owner"));
      }
      case "unshare": {
        const { w } = await load(["owner"]);
        const email = String(body.email ?? "").toLowerCase();
        const members = w.members.filter((m) => m.email !== email);
        const next = { ...w, members, member_emails: members.map((m) => m.email) };
        await db.Workbook.update(w.id, { members: next.members, member_emails: next.member_emails });
        return Response.json(view(next, "owner"));
      }
      case "delete": {
        const { w } = await load(["owner"]);
        await db.Workbook.delete(w.id);
        return Response.json({ deleted: w.id });
      }
      case "join": {
        // for the WorkbookRoom actor: who is this, and may they be in the room?
        const { role } = await load();
        return Response.json({ email: user.email, name: user.name, role });
      }
      default:
        throw new Fail(400, `Unknown action ${body.action}`);
    }
  } catch (e) {
    const status = e instanceof Fail ? e.status : 500;
    return Response.json({ detail: (e as Error).message }, { status });
  }
}

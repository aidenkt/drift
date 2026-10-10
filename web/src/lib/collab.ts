/** Shared workbooks on the engine: who you are, who a workbook is shared with, who has it open. */

const ENGINE = import.meta.env.VITE_ENGINE_URL ?? "http://localhost:8000";

export type Role = "owner" | "editor" | "viewer";
export type Me = { email: string; name: string };
export type SharedDoc = {
  doc_id: string;
  filename: string;
  owner: Me;
  members: { email: string; role: Exclude<Role, "owner"> }[];
  role: Role;
  updated: number;
  updated_by: string | null;
};
export type Person = Me & { role: Role; cell: string | null };

/* ---------- identity ---------- */

// Signed in with Clerk, AuthGate registers the user and a token getter. Without Clerk (local
// dev) each tab is its own guest, so two tabs show up as two people.
let clerk: { me: Me; token: () => Promise<string | null> } | null = null;
export const setClerkIdentity = (me: Me, token: () => Promise<string | null>) => {
  clerk = { me, token };
};

function guest(): Me {
  const saved = sessionStorage.getItem("since-guest");
  if (saved) return JSON.parse(saved);
  const id = Math.random().toString(36).slice(2, 6);
  const me = { email: `guest-${id}@since.local`, name: `Guest ${id.toUpperCase()}` };
  sessionStorage.setItem("since-guest", JSON.stringify(me));
  return me;
}

export const me = (): Me => clerk?.me ?? guest();

async function authHeaders(): Promise<Record<string, string>> {
  if (clerk) {
    const t = await clerk.token();
    return t ? { Authorization: `Bearer ${t}` } : {};
  }
  const g = guest();
  return { "X-Dev-User": g.email, "X-Dev-Name": g.name };
}

/* ---------- workbooks and access ---------- */

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${ENGINE}${path}`, { ...init, headers: { ...(init.headers ?? {}), ...(await authHeaders()) } });
  } catch {
    throw new Error(`Sharing needs the engine running at ${ENGINE}.`);
  }
  if (!res.ok) {
    const detail = await res.json().then((b) => b.detail, () => null);
    throw new Error(typeof detail === "string" ? detail : `${res.status} ${res.statusText}`);
  }
  return res.headers.get("content-type")?.includes("json") ? res.json() : (res.arrayBuffer() as Promise<T>);
}

const form = (bytes: ArrayBuffer, filename: string) => {
  const f = new FormData();
  f.append("file", new Blob([bytes]), filename);
  return f;
};

export const listShared = () => call<SharedDoc[]>("/workbooks");
export const createShared = (bytes: ArrayBuffer, filename: string) =>
  call<SharedDoc>("/workbooks", { method: "POST", body: form(bytes, filename) });
export const getShared = (id: string) => call<SharedDoc>(`/workbooks/${id}`);
export const fetchSharedFile = (id: string) => call<ArrayBuffer>(`/workbooks/${id}/file`);
export const saveShared = (id: string, bytes: ArrayBuffer, filename: string) =>
  call<{ updated: number }>(`/workbooks/${id}/file`, { method: "PUT", body: form(bytes, filename) });
export const shareWith = (id: string, email: string, role: "editor" | "viewer") =>
  call<SharedDoc>(`/workbooks/${id}/members`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, role }),
  });
export const unshare = (id: string, email: string) =>
  call<SharedDoc>(`/workbooks/${id}/members/${encodeURIComponent(email)}`, { method: "DELETE" });

/* ---------- presence ---------- */

type Handlers = { onPeople: (p: Person[]) => void; onSaved: (by: { email: string; name: string }) => void; onError: (msg: string) => void };

/** Joins a workbook's presence room. Reconnects if the connection drops. */
export function joinPresence(id: string, h: Handlers) {
  let ws: WebSocket | null = null;
  let closed = false;
  let cell: string | null = null;
  let retry: number | undefined;

  const open = async () => {
    const q = new URLSearchParams();
    if (clerk) {
      const t = await clerk.token();
      if (t) q.set("token", t);
    } else {
      const g = guest();
      q.set("dev", g.email);
      q.set("name", g.name);
    }
    if (closed) return;
    ws = new WebSocket(`${ENGINE.replace(/^http/, "ws")}/workbooks/${id}/presence?${q}`);
    ws.onopen = () => cell && ws?.send(JSON.stringify({ type: "cell", cell }));
    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      if (msg.type === "presence") h.onPeople(msg.people);
      if (msg.type === "saved") h.onSaved({ email: msg.by, name: msg.name ?? msg.by });
    };
    ws.onclose = (e) => {
      if (closed) return;
      if (e.code === 4401 || e.code === 4403) return h.onError(e.reason || "No access to this workbook");
      retry = window.setTimeout(open, 2000);
    };
  };
  void open();

  return {
    setCell(next: string) {
      cell = next;
      if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "cell", cell }));
    },
    close() {
      closed = true;
      clearTimeout(retry);
      ws?.close();
    },
  };
}

/* ---------- avatars ---------- */

const COLORS = ["#1f47b8", "#0f8b8d", "#7a4cc2", "#c26a1b", "#2e7d32", "#b8326e", "#4d5bd1", "#8a6d00"];

/** A stable colour per person, so they look the same in every tab. */
export function colorFor(email: string): string {
  let h = 0;
  for (const ch of email) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return COLORS[h % COLORS.length];
}

export const initials = (name: string) =>
  name
    .replace(/@.*/, "")
    .split(/[\s._-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]!.toUpperCase())
    .join("");

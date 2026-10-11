/** Shared workbooks on Base44: who you are, who a workbook is shared with, who has it open and
 *  what they're doing in it.
 *  Sign-in stays with Clerk: every call carries the Clerk session token, and the `workbooks`
 *  function and WorkbookRoom actor (see /base44) check it. */
import { createClient } from "@base44/sdk";

const base44 = createClient({ appId: import.meta.env.VITE_BASE44_APP_ID ?? "6acaab66ecbcf0974bea29c3" });

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
/** cell: their active cell; range: what they've highlighted, when it's more than one cell
 *  ("P&L!C18:G18"); open: the id of the change they have open. */
export type Person = Me & { role: Role; cell: string | null; range: string | null; open: string | null };
export type Here = { cell: string | null; range: string | null; open: string | null };

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

/** Who's asking: the Clerk session token. Without Clerk (local dev) there's none, and sharing
 *  answers "Sign in to share". */
async function credentials(): Promise<{ token?: string }> {
  return clerk ? { token: (await clerk.token()) ?? undefined } : {};
}

/* ---------- workbooks and access ---------- */

async function call<T>(action: string, args: Record<string, unknown> = {}): Promise<T> {
  try {
    const res = await base44.functions.invoke("workbooks", { action, ...args, ...(await credentials()) });
    return res.data as T;
  } catch (e) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    throw new Error(err.response?.data?.detail ?? err.message ?? "Sharing is unavailable right now.");
  }
}

// workbook files travel as base64
const toBase64 = (bytes: ArrayBuffer) => {
  let s = "";
  const view = new Uint8Array(bytes);
  for (let i = 0; i < view.length; i += 0x8000) s += String.fromCharCode(...view.subarray(i, i + 0x8000));
  return btoa(s);
};
const fromBase64 = (b64: string) => Uint8Array.from(atob(b64), (c) => c.charCodeAt(0)).buffer;

export const listShared = () => call<SharedDoc[]>("list");
export const createShared = (bytes: ArrayBuffer, filename: string) => call<SharedDoc>("create", { filename, data: toBase64(bytes) });
export const getShared = (id: string) => call<SharedDoc>("get", { id });
export const fetchSharedFile = (id: string) => call<{ data: string }>("file", { id }).then((r) => fromBase64(r.data));
export const saveShared = (id: string, bytes: ArrayBuffer) => call<{ updated: number }>("save", { id, data: toBase64(bytes) });
export const shareWith = (id: string, email: string, role: "editor" | "viewer") => call<SharedDoc>("share", { id, email, role });
export const unshare = (id: string, email: string) => call<SharedDoc>("unshare", { id, email });

/* ---------- presence and live edits ---------- */

type Handlers = {
  onPeople: (p: Person[]) => void;
  /** Someone else's edit, as it happens (see lib/live). */
  onOp: (op: unknown, by: Me) => void;
  onError: (msg: string) => void;
};

// tells this tab's own edits apart when the room echoes them back
const TAB = Math.random().toString(36).slice(2, 10);

/** Joins a workbook's WorkbookRoom. The room asks who we are on every (re)connect. */
export function joinPresence(id: string, h: Handlers) {
  const room = base44.actors.WorkbookRoom(id).connect();
  let here: Here | null = null;
  const sub = room.subscribe((data) => {
    const msg = data as { type: string; people?: Person[]; by?: string; name?: string; detail?: string; from?: string; op?: unknown };
    if (msg.type === "hello?")
      void credentials().then((c) => {
        room.send({ type: "hello", ...c });
        if (here?.cell) room.send({ type: "cell", ...here });
      });
    if (msg.type === "presence") h.onPeople(msg.people ?? []);
    if (msg.type === "op" && msg.from !== TAB) h.onOp(msg.op, { email: msg.by ?? "", name: msg.name ?? msg.by ?? "" });
    if (msg.type === "error") h.onError(msg.detail ?? "No access to this workbook");
  });

  return {
    /** Where we are: the active cell, the highlighted range, the open change. */
    setHere(next: Here) {
      here = next;
      if (next.cell) room.send({ type: "cell", ...next });
    },
    /** Send an edit to everyone else in the room. */
    send(op: unknown) {
      room.send({ type: "op", from: TAB, op });
    },
    /** Tell the others a new version was saved. */
    saved() {
      room.send({ type: "saved" });
    },
    close() {
      sub.unsubscribe();
      room.close();
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

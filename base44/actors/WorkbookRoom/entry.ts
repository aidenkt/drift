// Who has a workbook open right now, what each person has highlighted, and their edits as they
// happen. One room per workbook.
//
// Visitors connect anonymously (Since signs in with Clerk, not Base44), then say hello with their
// Clerk session token. Actors can't read secrets, so the `workbooks` function checks the token
// and the person's access; only then do they appear in the room.
import { Actor } from "base44:runtime/actors";

// cell: the active cell; range: the highlighted range when it's more than one cell ("P&L!C18:G18");
// open: the change they have open in the side panel
type Person = { email: string; name: string; role: string; cell: string | null; range: string | null; open: string | null };
const short = (v: unknown) => (typeof v === "string" && v.length <= 64 ? v : null);

export default class WorkbookRoom extends Actor {
  people = new Map<string, Person>(); // conn.id -> person, once they've said hello

  async handleStart() {
    // a quiet room hibernates and forgets its fields; sockets can stay attached through that
    this.people = new Map((await this.storage.get("people")) ?? []);
    const live = new Set(this.getConnections().map((c: { id: string }) => c.id));
    if (live.size > 0) {
      for (const id of this.people.keys()) if (!live.has(id)) this.people.delete(id);
      await this.save();
    }
  }

  async handleConnect(conn: { id: string; send: (m: unknown) => void }) {
    // a reconnect reclaims its place; anyone else waits for hello
    if (this.people.has(conn.id)) this.announce();
    else conn.send({ type: "hello?" });
  }

  async handleMessage(conn: { id: string; send: (m: unknown) => void }, msg: unknown) {
    if (typeof msg !== "object" || msg === null) return;
    const m = msg as Record<string, unknown>;

    if (m.type === "hello") {
      try {
        const res = await this.client.functions.invoke("workbooks", {
          action: "join",
          id: this.instanceId,
          token: typeof m.token === "string" ? m.token : undefined,
        });
        const who = res.data as { email: string; name: string; role: string };
        this.people.set(conn.id, { ...who, cell: null, range: null, open: null });
        await this.save();
        this.announce();
      } catch (e) {
        const detail = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? "No access to this workbook";
        conn.send({ type: "error", detail });
      }
      return;
    }

    const me = this.people.get(conn.id);
    if (!me) return; // hasn't been let in

    if (m.type === "cell" && short(m.cell)) {
      me.cell = short(m.cell);
      me.range = short(m.range);
      me.open = short(m.open);
      this.announce(); // cursor moves are frequent: broadcast, don't persist
    } else if (m.type === "op" && me.role !== "viewer") {
      // live edits go to everyone; `from` is the sending tab, which skips its own
      this.broadcast({ type: "op", from: short(m.from), by: me.email, name: me.name, op: m.op });
    } else if (m.type === "saved") {
      this.broadcast({ type: "saved", by: me.email, name: me.name });
    }
  }

  async handleClose(conn: { id: string }) {
    if (!this.people.delete(conn.id)) return;
    await this.save();
    this.announce();
  }

  save() {
    return this.storage.put("people", [...this.people.entries()]);
  }

  /** One entry per person, even with the workbook open in several tabs; latest cell wins. */
  announce() {
    const byEmail = new Map<string, Person>();
    for (const p of this.people.values()) byEmail.set(p.email, p);
    this.broadcast({
      type: "presence",
      people: [...byEmail.values()].map((p) => ({ email: p.email, name: p.name, role: p.role, cell: p.cell, range: p.range ?? null, open: p.open ?? null })),
    });
  }
}

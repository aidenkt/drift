// Who has a workbook open right now, and which cell each person is on. One room per workbook.
//
// Visitors connect anonymously (Since signs in with Clerk, not Base44), then say hello with their
// Clerk session token. Actors can't read secrets, so the `workbooks` function checks the token
// and the person's access; only then do they appear in the room.
import { Actor } from "base44:runtime/actors";

type Person = { email: string; name: string; role: string; cell: string | null };

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
        this.people.set(conn.id, { ...who, cell: null });
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

    if (m.type === "cell" && typeof m.cell === "string" && m.cell.length <= 64) {
      me.cell = m.cell;
      this.announce(); // cursor moves are frequent: broadcast, don't persist
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
      people: [...byEmail.values()].map((p) => ({ email: p.email, name: p.name, role: p.role, cell: p.cell })),
    });
  }
}

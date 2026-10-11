import { useEffect, useRef, useState, type FormEvent } from "react";
import { colorFor, initials, me, shareWith, unshare, type SharedDoc } from "../lib/collab";

type Props = {
  filename: string;
  doc: SharedDoc | null; // null until the first invite uploads the workbook
  ensureDoc: () => Promise<SharedDoc>;
  onChange: (doc: SharedDoc) => void;
  onClose: () => void;
};

const ROLE_LABEL = { owner: "Owner", editor: "Can edit", viewer: "Can view" } as const;

/** Share a workbook with specific people by email, Google Docs style. */
export default function ShareDialog({ filename, doc, ensureDoc, onChange, onClose }: Props) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"editor" | "viewer">("editor");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const isOwner = !doc || doc.role === "owner";

  useEffect(() => {
    dialog.current?.showModal();
  }, []);

  const run = async (op: () => Promise<SharedDoc>) => {
    setBusy(true);
    setError(null);
    try {
      onChange(await op());
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return false;
    } finally {
      setBusy(false);
    }
  };

  const invite = async (e: FormEvent) => {
    e.preventDefault();
    const address = email.trim();
    if (!address) return;
    const ok = await run(async () => shareWith((await ensureDoc()).doc_id, address, role));
    if (ok) setEmail("");
  };

  const owner = doc?.owner ?? me();
  const people = [
    { email: owner.email, name: owner.name, role: "owner" as const },
    ...(doc?.members ?? []).map((m) => ({ email: m.email, name: m.email, role: m.role })),
  ];

  return (
    <dialog ref={dialog} className="share-dialog" onClose={onClose} onCancel={onClose}>
      <header>
        <h2>Share “{filename.replace(/\.(xlsx|xlsm|xls)$/i, "")}”</h2>
        <button className="share-x" onClick={() => dialog.current?.close()} aria-label="Close">
          ×
        </button>
      </header>

      {isOwner ? (
        <form className="share-add" onSubmit={invite}>
          <input
            type="email"
            placeholder="Add people by email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            aria-label="Email address"
            autoFocus
          />
          <select value={role} onChange={(e) => setRole(e.target.value as "editor" | "viewer")} aria-label="Access">
            <option value="editor">Can edit</option>
            <option value="viewer">Can view</option>
          </select>
          <button className="btn" disabled={busy || !email.trim()}>
            {busy ? "Sharing…" : "Share"}
          </button>
        </form>
      ) : (
        <p className="share-note">Only the owner can change who has access.</p>
      )}
      {error && (
        <p className="share-error" role="alert">
          {error}
        </p>
      )}

      <h3>People with access</h3>
      <ul className="share-people">
        {people.map((p) => (
          <li key={p.email}>
            <span className="avatar" style={{ background: colorFor(p.email) }} aria-hidden>
              {initials(p.name)}
            </span>
            <span className="share-who">
              <span>
                {p.name}
                {p.email === me().email && <span className="muted"> (you)</span>}
              </span>
              {p.name !== p.email && <span className="muted small">{p.email}</span>}
            </span>
            {p.role === "owner" || !isOwner || !doc ? (
              <span className="muted">{ROLE_LABEL[p.role]}</span>
            ) : (
              <select
                value={p.role}
                aria-label={`Access for ${p.email}`}
                disabled={busy}
                onChange={(e) => {
                  const next = e.target.value;
                  void run(() => (next === "remove" ? unshare(doc.doc_id, p.email) : shareWith(doc.doc_id, p.email, next as "editor" | "viewer")));
                }}
              >
                <option value="editor">Can edit</option>
                <option value="viewer">Can view</option>
                <option value="remove">Remove access</option>
              </select>
            )}
          </li>
        ))}
      </ul>
    </dialog>
  );
}

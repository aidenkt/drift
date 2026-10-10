import { colorFor, initials, me, type Person } from "../lib/collab";

const MAX = 4;

/** Who has this workbook open right now, Google Docs style. You come first. */
export default function Presence({ people, onJump }: { people: Person[]; onJump: (cell: string) => void }) {
  const self = me().email;
  const sorted = [...people].sort((a, b) => Number(b.email === self) - Number(a.email === self));
  const extra = sorted.length - MAX;

  return (
    <div className="presence" aria-label={`${people.length} ${people.length === 1 ? "person" : "people"} viewing`}>
      {sorted.slice(0, MAX).map((p) => (
        <button
          key={p.email}
          className="avatar"
          style={{ background: colorFor(p.email) }}
          title={`${p.name}${p.email === self ? " (you)" : ""}${p.cell ? ` · on ${p.cell}` : ""}`}
          onClick={() => p.cell && p.email !== self && onJump(p.cell)}
        >
          {initials(p.name)}
        </button>
      ))}
      {extra > 0 && <span className="avatar more">+{extra}</span>}
    </div>
  );
}

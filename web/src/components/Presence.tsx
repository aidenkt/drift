import { colorFor, initials, me, type Person } from "../lib/collab";

const MAX = 4;

/** Who has this workbook open right now, Google Docs style. You come first.
 *  Clicking someone takes you to what they're looking at. */
export default function Presence({ people, where, onJump }: { people: Person[]; where: (p: Person) => string | null; onJump: (p: Person) => void }) {
  const self = me().email;
  const sorted = [...people].sort((a, b) => Number(b.email === self) - Number(a.email === self));
  const extra = sorted.length - MAX;

  return (
    <div className="presence" aria-label={`${people.length} ${people.length === 1 ? "person" : "people"} viewing`}>
      {sorted.slice(0, MAX).map((p) => {
        const at = where(p);
        return (
          <button
            key={p.email}
            className="avatar"
            style={{ background: colorFor(p.email) }}
            title={`${p.name}${p.email === self ? " (you)" : ""}${at ? ` · on ${at}` : ""}`}
            onClick={() => at && p.email !== self && onJump(p)}
          >
            {initials(p.name)}
          </button>
        );
      })}
      {extra > 0 && <span className="avatar more">+{extra}</span>}
    </div>
  );
}

/** Small stacked avatars for the people on one thing: a change card, an open change. */
export function Faces({ people }: { people: { email: string; name: string }[] }) {
  if (!people.length) return null;
  return (
    <span className="faces" title={people.map((p) => p.name).join(", ")}>
      {people.slice(0, 3).map((p) => (
        <span key={p.email} className="face" style={{ background: colorFor(p.email) }}>
          {initials(p.name)}
        </span>
      ))}
    </span>
  );
}

import type { TimelineEvent } from "../data/timeline";
import { deltaMoney, shortDate, value } from "../lib/format";

type Props = {
  events: TimelineEvent[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  sample: boolean;
};

const MARK: Record<TimelineEvent["status"], string> = {
  stale: "Stale",
  watching: "Watching",
  current: "Current",
  edited: "Edited",
};

export default function Timeline({ events, selectedId, onSelect, sample }: Props) {
  return (
    <aside className="timeline" aria-label="Changes to this model's assumptions">
      <header className="timeline-head">
        <h2>Changes</h2>
        {sample && <span className="sample-tag">case study</span>}
      </header>

      {events.length === 0 ? (
        <p className="timeline-empty">Edits and checks on this model show up here.</p>
      ) : (
        <ol className="timeline-list">
          {events.map((e) => (
            <li key={e.id}>
              <button
                className={`tl-item ${e.status} ${e.id === selectedId ? "on" : ""}`}
                onClick={() => onSelect(e.id)}
                aria-current={e.id === selectedId ? "true" : undefined}
              >
                <span className="tl-dot" aria-hidden />
                <span className="tl-date mono">{shortDate(e.date)}</span>
                <span className="tl-title">{e.title}</span>
                <span className="sr-only">{MARK[e.status]}.</span>
                <Delta e={e} />
                <span className="tl-foot">
                  <Effect e={e} />
                  <span className="mono">{e.cells.length === 1 ? e.cells[0] : `${e.cells.length} assumptions`}</span>
                </span>
              </button>
            </li>
          ))}
        </ol>
      )}
    </aside>
  );
}

/** Model value → today's value, and how far it moved. */
function Delta({ e }: { e: TimelineEvent }) {
  if (e.edit)
    return (
      <span className="tl-delta mono">
        {e.edit.before || "empty"} <span className="tl-arrow">→</span> {e.edit.after || "empty"}
      </span>
    );
  const s = e.state;
  if (!s) return null;
  const unchanged = s.live === s.model;
  return (
    <span className="tl-delta mono">
      <span className="input">{value(s.model, s.unit)}</span>
      {!unchanged && s.live != null && (
        <>
          {" "}
          <span className="tl-arrow">→</span> {value(s.live, s.unit)}
        </>
      )}
      <span className={`tl-change ${e.status === "stale" ? "adverse" : ""}`}>{unchanged ? "unchanged" : s.change}</span>
    </span>
  );
}

/** The largest dollar effect on an output, EBITDA first. */
function Effect({ e }: { e: TimelineEvent }) {
  const moved = e.impact.filter((i) => i.delta !== 0);
  if (!moved.length) return null;
  const top = moved.find((i) => i.label === "EBITDA") ?? moved.reduce((a, b) => (Math.abs(b.delta) > Math.abs(a.delta) ? b : a));
  return (
    <span className={top.delta < 0 ? "tl-effect adverse" : "tl-effect"}>
      {top.label === "Enterprise value" ? "EV" : top.label} <span className="mono">{deltaMoney(top.delta)}</span>
    </span>
  );
}

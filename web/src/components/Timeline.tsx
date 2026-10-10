import type { TimelineEvent } from "../data/timeline";
import { shortDate } from "../lib/format";

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
                <span className="tl-meta mono">
                  <span className={`tl-status ${e.status}`}>{MARK[e.status]}</span>
                  {e.cells.length === 1 ? e.cells[0] : `${e.cells.length} cells`}
                  {e.sources.length > 0 && e.kind !== "baseline" && (
                    <span>
                      {e.sources.length} source{e.sources.length > 1 ? "s" : ""}
                    </span>
                  )}
                </span>
              </button>
            </li>
          ))}
        </ol>
      )}
    </aside>
  );
}

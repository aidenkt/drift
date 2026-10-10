import { useMemo, useRef, useState, useEffect } from "react";
import type { TimelineEvent } from "../data/timeline";
import { ago, clock, deltaMoney, shortDate, value } from "../lib/format";

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

/** Everything a search can match: title, cells, driver, values and sources. */
function haystack(e: TimelineEvent): string {
  return [
    e.title,
    MARK[e.status],
    e.driver,
    ...e.cells,
    e.state?.label,
    e.state && value(e.state.model, e.state.unit),
    e.state?.live != null ? value(e.state.live, e.state.unit) : null,
    e.edit?.before,
    e.edit?.after,
    ...e.sources.flatMap((s) => [s.publisher, s.title, s.value, s.via]),
    ...e.impact.map((i) => i.label),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

export default function Timeline({ events, selectedId, onSelect, sample }: Props) {
  const [query, setQuery] = useState("");
  const search = useRef<HTMLInputElement>(null);

  const shown = useMemo(() => {
    const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
    return terms.length ? events.filter((e) => terms.every((t) => haystack(e).includes(t))) : events;
  }, [events, query]);

  // "/" jumps to search, like most review tools
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = (e.target as HTMLElement).closest("input, textarea, [contenteditable], .grid");
      if (e.key === "/" && !typing) {
        e.preventDefault();
        search.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <aside className="timeline" aria-label="Changes to this model's assumptions">
      <header className="timeline-head">
        <h2>Changes</h2>
        {sample && <span className="sample-tag">case study</span>}
      </header>

      <div className="timeline-search">
        <input
          ref={search}
          type="search"
          value={query}
          placeholder="Search changes, cells, sources"
          aria-label="Search changes"
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Escape" && setQuery("")}
        />
        {query && (
          <span className="search-count mono" aria-live="polite">
            {shown.length} of {events.length}
          </span>
        )}
      </div>

      {events.length === 0 ? (
        <p className="timeline-empty">Edits and checks on this model show up here.</p>
      ) : shown.length === 0 ? (
        <p className="timeline-empty">No changes match "{query}". Try a cell like B21, a driver like freight, or a source like FRED.</p>
      ) : (
        <ol className="timeline-list">
          {shown.map((e) => (
            <li key={e.id}>
              <button
                className={`tl-item ${e.status} ${e.id === selectedId ? "on" : ""}`}
                onClick={() => onSelect(e.id)}
                aria-current={e.id === selectedId ? "true" : undefined}
              >
                <span className="tl-dot" aria-hidden />
                <When e={e} />
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

/** When the change happened: date and age, or time and author for edits made here. */
function When({ e }: { e: TimelineEvent }) {
  const label = ago(e.date);
  const day = label === "Today" || label === "Yesterday" ? label : shortDate(e.date);
  return (
    <span className="tl-date">
      <time className="mono" dateTime={e.at ?? e.date}>
        {e.at ? `${day} ${clock(e.at)}` : day}
      </time>
      {e.at ? e.by && <span>by {e.by.toLowerCase() === "you" ? "you" : e.by}</span> : day !== label && <span>{label}</span>}
    </span>
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

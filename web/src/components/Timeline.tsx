import { useLayoutEffect, useMemo, useRef, useState, useEffect } from "react";
import type { TimelineEvent } from "../data/timeline";
import { inRange, parseQuery } from "../lib/dates";
import { ago, clock, deltaMoney, shortDate, value } from "../lib/format";

type Props = {
  events: TimelineEvent[];
  selectedId: string | null;
  onSelect: (id: string) => void;
};

const MARK: Record<TimelineEvent["status"], string> = {
  stale: "Stale",
  watching: "Watching",
  current: "Current",
  edited: "Edited",
};

/** Everything a search can match: title, cells, driver, values, sources and dates. */
function haystack(e: TimelineEvent): string {
  return [
    e.title,
    e.date,
    shortDate(e.date),
    ago(e.date),
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

export default function Timeline({ events, selectedId, onSelect }: Props) {
  const [query, setQuery] = useState("");
  const [staleOnly, setStaleOnly] = useState(false);
  const staleCount = events.filter((e) => e.status === "stale").length;
  const search = useRef<HTMLInputElement>(null);

  // date phrases ("oct 8", "last week", "after:sep 15") filter by when; the rest is text
  const parsed = useMemo(() => parseQuery(query), [query]);
  const shown = useMemo(
    () =>
      events.filter(
        (e) =>
          (!staleOnly || e.status === "stale") &&
          parsed.ranges.every((r) => inRange(e.date, r)) &&
          parsed.terms.every((t) => haystack(e).includes(t)),
      ),
    [events, parsed, staleOnly],
  );

  // one highlight that glides to the selected change instead of jumping
  const list = useRef<HTMLDivElement>(null);
  const [marker, setMarker] = useState<{ top: number; height: number; moved: boolean } | null>(null);
  useLayoutEffect(() => {
    const on = list.current?.querySelector<HTMLElement>(".tl-item.on");
    if (!on) return setMarker(null);
    on.scrollIntoView({ block: "nearest", behavior: "smooth" });
    const place = () => setMarker((m) => ({ top: on.offsetTop, height: on.offsetHeight, moved: m != null }));
    place();
    const ro = new ResizeObserver(place);
    ro.observe(on);
    return () => ro.disconnect();
  }, [selectedId, shown]);

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
        {staleCount > 0 && (
          <button
            className={`tl-filter ${staleOnly ? "on" : ""}`}
            aria-pressed={staleOnly}
            onClick={() => setStaleOnly((v) => !v)}
          >
            <span className="tl-filter-dot" aria-hidden />
            Stale <span className="mono">{staleCount}</span>
          </button>
        )}
      </header>

      <div className="timeline-search">
        <input
          ref={search}
          type="search"
          value={query}
          placeholder="Search changes, cells, sources, dates"
          aria-label="Search changes"
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Escape" && setQuery("")}
        />
        {(query || staleOnly) && (
          <span className="search-count mono" aria-live="polite">
            {shown.length} of {events.length}
          </span>
        )}
        {parsed.ranges.length > 0 && (
          <p className="search-dates">
            Dated {parsed.ranges.map((r) => r.label).join(", ")}
          </p>
        )}
      </div>

      {events.length === 0 ? (
        <p className="timeline-empty">Edits and checks on this model show up here.</p>
      ) : shown.length === 0 ? (
        <p className="timeline-empty">
          {query
            ? `No ${staleOnly ? "stale " : ""}changes match "${query}". Try a cell like B21, a source like FRED, or a date like "last week" or "after:sep 15".`
            : "Nothing is stale. Every assumption matches its source."}
        </p>
      ) : (
        <div className="timeline-scroll" ref={list}>
          {marker && (
            <span
              className={`tl-marker ${marker.moved ? "glide" : ""}`}
              aria-hidden
              style={{ transform: `translateY(${marker.top}px)`, height: marker.height }}
            />
          )}
          <ol className="timeline-list">
            {shown.map((e) => (
              <li key={e.id}>
                <button
                  className={`tl-item ${e.status} ${e.id === selectedId ? "on" : ""}`}
                  onClick={() => onSelect(e.id)}
                  aria-current={e.id === selectedId ? "true" : undefined}
                >
                  <span className="tl-row">
                    <span className="tl-title">{e.title}</span>
                    <span className={`tl-badge ${e.status}`}>{MARK[e.status]}</span>
                  </span>
                  <Delta e={e} />
                  <span className="tl-foot">
                    <When e={e} />
                    <Effect e={e} />
                  </span>
                </button>
              </li>
            ))}
          </ol>
        </div>
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

/** Cell, model value → today's value, and how far it moved. */
function Delta({ e }: { e: TimelineEvent }) {
  const cell = <span className="tl-cell">{e.cells.length === 1 ? e.cells[0] : `${e.cells.length} cells`}</span>;
  if (e.edit)
    return (
      <span className="tl-row tl-delta mono">
        <span className="tl-values">
          {cell}
          <span>{e.edit.before || "empty"}</span>
          <span className="tl-arrow">→</span>
          <span>{e.edit.after || "empty"}</span>
        </span>
      </span>
    );
  const s = e.state;
  const unchanged = s ? s.live === s.model : true;
  return (
    <span className="tl-row tl-delta mono">
      <span className="tl-values">
        {cell}
        {s && <span className="input">{value(s.model, s.unit)}</span>}
        {s && !unchanged && s.live != null && (
          <>
            <span className="tl-arrow">→</span>
            <span>{value(s.live, s.unit)}</span>
          </>
        )}
      </span>
      {s && <span className={`tl-change ${e.status}`}>{unchanged ? "unchanged" : s.change}</span>}
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

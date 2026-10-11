import { useLayoutEffect, useMemo, useRef, useState, useEffect } from "react";
import type { TimelineEvent } from "../data/timeline";
import { inRange, parseQuery } from "../lib/dates";
import { ago, clock, deltaMoney, shortDate, value } from "../lib/format";
import { Faces } from "./Presence";

type Props = {
  events: TimelineEvent[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  /** change id -> the other people who have it open */
  viewers?: Map<string, { email: string; name: string }[]>;
};

const MARK: Record<TimelineEvent["status"], string> = {
  stale: "Stale",
  watching: "Watching",
  current: "Current",
  edited: "Edited",
  updated: "Updated",
  kept: "Kept",
  gone: "Removed",
};

/** A stale assumption that's been dealt with: it moves to the Resolved group. */
const resolved = (e: TimelineEvent) => e.status === "updated" || e.status === "kept" || e.status === "gone";

/** Checked and still matching its source: nothing to do, so it waits in its own group. */
const quiet = (e: TimelineEvent) => e.status === "current";

/** The output effect a card leads with and sorts by: enterprise value, as on the home page, else the largest. */
function topEffect(e: TimelineEvent) {
  const moved = e.impact.filter((i) => i.delta !== 0);
  if (!moved.length) return null;
  return moved.find((i) => i.label === "Enterprise value") ?? moved.reduce((a, b) => (Math.abs(b.delta) > Math.abs(a.delta) ? b : a));
}

/** Stale changes in the order the list shows them: biggest dollar effect first. */
export function reviewOrder(events: TimelineEvent[]): TimelineEvent[] {
  return events.filter((e) => e.status === "stale").sort((a, b) => Math.abs(topEffect(b)?.delta ?? 0) - Math.abs(topEffect(a)?.delta ?? 0));
}

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
    e.resolution?.note,
    ...e.sources.flatMap((s) => [s.publisher, s.title, s.value, s.via]),
    ...e.impact.map((i) => i.label),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

export default function Timeline({ events, selectedId, onSelect, viewers }: Props) {
  const [query, setQuery] = useState("");
  const [staleOnly, setStaleOnly] = useState(false);
  const staleCount = events.filter((e) => e.status === "stale").length;
  const search = useRef<HTMLInputElement>(null);
  const [showResolved, setShowResolved] = useState(false);
  const [showCurrent, setShowCurrent] = useState(false);

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
  // stale first, biggest dollar effect on top; current and resolved collapse at the bottom
  const size = (e: TimelineEvent) => (e.status === "stale" ? Math.abs(topEffect(e)?.delta ?? 0) : -1);
  const open = shown.filter((e) => !resolved(e) && !quiet(e)).sort((a, b) => size(b) - size(a));
  const current = shown.filter(quiet);
  const done = shown.filter(resolved);
  const currentOpen = showCurrent || current.some((e) => e.id === selectedId);
  const doneOpen = showResolved || done.some((e) => e.id === selectedId);

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
  }, [selectedId, shown, doneOpen, currentOpen]);

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

  const item = (e: TimelineEvent) => (
    <li key={e.id}>
      <button
        className={`tl-item ${e.status} ${e.id === selectedId ? "on" : ""}`}
        onClick={() => onSelect(e.id)}
        aria-current={e.id === selectedId ? "true" : undefined}
      >
        <span className="tl-row">
          <span className="tl-title">{e.title}</span>
          <Faces people={viewers?.get(e.id) ?? []} />
          <span className={`tl-badge ${e.status}`}>{MARK[e.status]}</span>
        </span>
        <Delta e={e} />
        {e.resolution && (
          <span className={`tl-resolution ${e.status}`}>
            {e.status === "updated" && "✓ "}
            {e.resolution.note}
            {e.resolution.at && ` · ${e.resolution.by === "You" ? "you" : e.resolution.by} ${clock(e.resolution.at)}`}
          </span>
        )}
        <span className="tl-foot">
          <When e={e} />
          {!resolved(e) && <Effect e={e} />}
        </span>
      </button>
    </li>
  );

  const group = (label: string, list: TimelineEvent[], expanded: boolean, toggle: () => void) =>
    list.length > 0 && (
      <>
        <button className="tl-group" aria-expanded={expanded} onClick={toggle}>
          <span className="tl-group-caret" aria-hidden>
            {expanded ? "▾" : "▸"}
          </span>
          {label} <span className="mono">{list.length}</span>
        </button>
        {expanded && <ol className="timeline-list resolved">{list.map(item)}</ol>}
      </>
    );

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
          <ol className="timeline-list">{open.map(item)}</ol>
          {group("Current", current, currentOpen, () => setShowCurrent((v) => !v))}
          {group("Resolved", done, doneOpen, () => setShowResolved((v) => !v))}
        </div>
      )}
    </aside>
  );
}

/** When the change happened, plus who made it for edits made here. */
function When({ e }: { e: TimelineEvent }) {
  const label = ago(e.date);
  const day = label === "Today" || label === "Yesterday" ? label : shortDate(e.date);
  return (
    <span className="tl-date">
      <time className="mono" dateTime={e.at ?? e.date}>
        {e.at ? `${day} ${clock(e.at)}` : day}
      </time>
      {e.at && e.by && <span>by {e.by.toLowerCase() === "you" ? "you" : e.by}</span>}
    </span>
  );
}

/** Model value → today's value, and how far it moved. The cell ref lives in the open change. */
function Delta({ e }: { e: TimelineEvent }) {
  if (e.edit)
    return (
      <span className="tl-row tl-delta mono">
        <span className="tl-values">
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

/** The dollar effect the card leads with. */
function Effect({ e }: { e: TimelineEvent }) {
  const top = topEffect(e);
  if (!top) return null;
  return (
    <span className={top.delta < 0 ? "tl-effect adverse" : "tl-effect"}>
      {top.label === "Enterprise value" ? "EV" : top.label} <span className="mono">{deltaMoney(top.delta)}</span>
    </span>
  );
}

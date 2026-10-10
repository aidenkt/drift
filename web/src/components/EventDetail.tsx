import { useMemo } from "react";
import type { Source, TimelineEvent } from "../data/timeline";
import { deltaMoney, money, value } from "../lib/format";
import { liveUpdates, whatIf, type Book, type CellUpdate } from "../lib/workbook";
import { Close } from "./icons";
import Stamp from "./Stamp";

type Props = {
  event: TimelineEvent;
  book: Book;
  rev: number;
  applied: boolean;
  onShowCell: (ref: string) => void;
  onApply: (event: TimelineEvent, updates: CellUpdate[]) => void;
  onClose: () => void;
};

/** Inspector for one change, docked beside the sheet: the numbers, what updating does, and why. */
export default function EventDetail({ event: e, book, rev, applied, onShowCell, onApply, onClose }: Props) {
  const s = e.state;
  const cell = e.cells[0];
  const stale = e.status === "stale" && !applied;

  // the writes that bring the cell up to date, and the outputs recomputed with them
  const updates = useMemo(
    () => (stale && s?.live != null && cell ? liveUpdates(book, cell, s.model, s.live) : []),
    [book, cell, s, stale, rev],
  );
  const effects = useMemo(
    () => (updates.length ? whatIf(book, updates, e.impact.map((i) => i.output)) : []),
    [book, updates, e.impact],
  );
  const target = updates.length > 1 ? `${updates[0].cell}:${updates.at(-1)!.cell.split("!")[1]}` : cell;

  return (
    <section className="inspector" aria-label={s?.label ?? e.title}>
      <header className="ins-bar">
        <span className="mono muted">{e.date}</span>
        <button className="ins-close" onClick={onClose} aria-label="Close" title="Close (Esc)">
          <Close />
        </button>
      </header>

      <div className="ins-head">
        <div className="ins-status">
          {applied ? <span className="ins-done">Updated</span> : e.status === "stale" ? <Stamp status="stale" /> : <span className="muted">{e.status}</span>}
        </div>
        <h2 className="ins-label">{s?.label ?? e.title}</h2>
        <div className="ins-cells">
          {e.cells.map((c) => (
            <button key={c} className="cell-chip mono" onClick={() => onShowCell(c)} title="Show in sheet">
              {c}
            </button>
          ))}
          {s && <span className="muted">{s.unit}</span>}
        </div>
      </div>

      {s && (
        <div className="ins-values mono">
          <div>
            <span>in model</span>
            <strong className="input">{value(s.model, s.unit)}</strong>
          </div>
          <div>
            <span>now · {s.as_of}</span>
            <strong>{s.live != null ? value(s.live, s.unit) : "—"}</strong>
          </div>
          <div>
            <span>change</span>
            <strong className={e.status === "stale" ? "stale-text" : undefined}>{s.change ?? "—"}</strong>
          </div>
        </div>
      )}

      {e.edit && (
        <div className="ins-values mono">
          <div>
            <span>before</span>
            <strong>{e.edit.before || "empty"}</strong>
          </div>
          <div>
            <span>after</span>
            <strong>{e.edit.after || "empty"}</strong>
          </div>
        </div>
      )}

      {effects.length > 0 && (
        <div className="ins-section">
          <h3>If updated</h3>
          <table className="ins-table mono">
            <thead>
              <tr>
                <th />
                <th>now</th>
                <th>after</th>
                <th>change</th>
              </tr>
            </thead>
            <tbody>
              {effects.map((x) => {
                const label = e.impact.find((i) => i.output === x.output)?.label ?? x.output;
                const d = x.before != null && x.after != null ? x.after - x.before : null;
                return (
                  <tr key={x.output}>
                    <td className="sans">{label}</td>
                    <td className="muted">{x.before != null ? money(x.before) : "—"}</td>
                    <td>{x.after != null ? money(x.after) : "—"}</td>
                    <td className={`num ${d != null && d < 0 ? "adverse" : ""}`}>{d != null ? deltaMoney(d) : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {updates.length > 0 && s?.live != null && (
        <button className="btn ins-apply" onClick={() => onApply(e, updates)}>
          Update {target} to {value(s.live, s.unit)}
        </button>
      )}

      {e.signals.length > 0 && (
        <div className="ins-section">
          <h3>Checks</h3>
          <ul className="ins-checks">
            {e.signals.map((sig) => (
              <li key={sig.look_for} className={sig.met ? "met" : ""}>
                <span className="sig-mark" aria-label={sig.met ? "Seen" : "Not seen"}>
                  {sig.met ? "●" : "○"}
                </span>
                <span>{sig.look_for}</span>
                <span className="sig-seen mono">{sig.observed}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {e.sources.length > 0 && (
        <div className="ins-section">
          <h3>Sources</h3>
          <ul className="ins-sources">
            {e.sources.map((src) => (
              <li key={src.title + src.url}>
                <SourceCard src={src} />
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

/** A source as an article card: its image, the headline, then the site it came from. */
function SourceCard({ src }: { src: Source }) {
  const site = src.url ? new URL(src.url).hostname.replace(/^www\./, "") : src.via;
  const body = (
    <>
      <span className="src-image" aria-hidden>
        {src.image ? <img src={src.image} alt="" loading="lazy" /> : <span className="src-mark">{src.publisher}</span>}
        {src.value && <span className="src-value mono">{src.value}</span>}
      </span>
      <span className="src-title">{src.title}</span>
      <span className="src-site">
        <span>{site}</span>
        <span className="mono">{src.date}</span>
      </span>
    </>
  );
  return src.url ? (
    <a className="src-card" href={src.url} target="_blank" rel="noreferrer">
      {body}
    </a>
  ) : (
    <div className="src-card">{body}</div>
  );
}

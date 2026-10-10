import type { TimelineEvent } from "../data/timeline";
import { deltaMoney, value } from "../lib/format";
import Sparkline from "./Sparkline";
import Stamp from "./Stamp";

type Props = {
  event: TimelineEvent;
  onShowCell: (ref: string) => void;
  onClose: () => void;
};

export default function EventDetail({ event: e, onShowCell, onClose }: Props) {
  const s = e.state;
  const stale = e.status === "stale";

  return (
    <section className="detail" aria-labelledby="detail-title">
      <header className="detail-head">
        <div className="detail-topline">
          <span className="mono muted">{e.date}</span>
          {e.status === "stale" ? <Stamp status="stale" /> : <span className="muted">{e.status}</span>}
          <span className="bar-spacer" />
          <button className="btn-line" onClick={onClose}>
            Back to sheet
          </button>
        </div>
        <h1 id="detail-title" className="detail-title">
          {e.title}
        </h1>
        <div className="detail-cells">
          {e.cells.map((c) => (
            <button key={c} className="cell-chip mono" onClick={() => onShowCell(c)} title="Show in sheet">
              {c}
            </button>
          ))}
        </div>
      </header>

      <div className="detail-grid">
        {s && (
          <div className="panel state">
            <h3>Current state</h3>
            <p className="state-label">
              {s.label} <span className="muted">{s.unit}</span>
            </p>
            <div className="state-values mono">
              <div>
                <span className="muted">in model</span>
                <strong className="input">{value(s.model, s.unit)}</strong>
              </div>
              <div>
                <span className="muted">now</span>
                <strong>{s.live != null ? value(s.live, s.unit) : "—"}</strong>
              </div>
              <div>
                <span className="muted">change</span>
                <strong className={stale ? "adverse" : undefined}>{s.change ?? "—"}</strong>
              </div>
            </div>
            <Sparkline points={s.history} model={s.model} stale={stale} />
            <p className="mono muted small">as of {s.as_of}</p>
          </div>
        )}

        {e.edit && (
          <div className="panel state">
            <h3>Edit</h3>
            <div className="state-values mono">
              <div>
                <span className="muted">before</span>
                <strong>{e.edit.before || "empty"}</strong>
              </div>
              <div>
                <span className="muted">after</span>
                <strong>{e.edit.after || "empty"}</strong>
              </div>
            </div>
          </div>
        )}

        {e.signals.length > 0 && (
          <div className="panel signals">
            <h3>What we look for</h3>
            <ul>
              {e.signals.map((sig) => (
                <li key={sig.look_for} className={sig.met ? "met" : ""}>
                  <span className="sig-mark" aria-label={sig.met ? "Seen" : "Not seen"}>
                    {sig.met ? "●" : "○"}
                  </span>
                  <span className="sig-look">{sig.look_for}</span>
                  <span className="sig-seen mono">{sig.observed}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {e.impact.length > 0 && (
          <div className="panel impact">
            <h3>Effect on outputs</h3>
            <table>
              <tbody>
                {e.impact.map((i) => (
                  <tr key={i.output}>
                    <td>{i.label}</td>
                    <td className="mono muted">{i.output}</td>
                    <td className={`mono num ${i.delta < 0 ? "adverse" : ""}`}>{deltaMoney(i.delta)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {e.sources.length > 0 && (
        <div className="sources">
          <h3>Sources</h3>
          <div className="source-cards">
            {e.sources.map((src) => (
              <article key={src.title + src.url} className="source-card">
                <header>
                  <span className="src-publisher">{src.publisher}</span>
                  <span className="mono muted small">{src.date}</span>
                </header>
                {src.url ? (
                  <a className="src-title" href={src.url} target="_blank" rel="noreferrer">
                    {src.title}
                  </a>
                ) : (
                  <span className="src-title">{src.title}</span>
                )}
                {src.quote && <blockquote>{src.quote}</blockquote>}
                <footer className="mono small">
                  {src.value && <span className="src-value">{src.value}</span>}
                  <span className="muted">via {src.via}</span>
                </footer>
              </article>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

import { useMemo, useRef, useState } from "react";
import { Account } from "../components/AuthGate";
import ImportButton from "../components/ImportButton";
import SheetThumb from "../components/SheetThumb";
import Wordmark from "../components/Wordmark";
import { Table } from "lucide-react";
import { SAMPLE_TIMELINE } from "../data/timeline";
import { deltaMoney, editedAt, shortDate, value } from "../lib/format";
import type { Book } from "../lib/workbook";
import type { Report } from "../types";

/** A workbook on the home page: a checked model, or a file imported in this browser. */
export type Entry = {
  key: string;
  filename: string;
  builtOn: string | null;
  added: string | null; // ISO time, imported files only
  edited: string | null; // ISO time: an edit made here, else when the file was last saved
  book: Book;
  report: Report | null;
};

type Props = {
  entries: Entry[] | null;
  onOpen: (e: Entry, startEvent?: string) => void;
  onImport: (file: File) => void;
  onRemove: (e: Entry) => void;
};

const staleCount = (e: Entry) => e.report?.constants.filter((c) => c.check?.status === "stale").length ?? 0;
const title = (filename: string) => filename.replace(/\.(xlsx|xlsm|xls)$/i, "");

export default function ModelList({ entries, onOpen, onImport, onRemove }: Props) {
  const [query, setQuery] = useState("");
  const [layout, setLayout] = useState<"grid" | "list">("grid");
  const file = useRef<HTMLInputElement>(null);

  const shown = (entries ?? []).filter((e) => e.filename.toLowerCase().includes(query.trim().toLowerCase()));
  const stale = (entries ?? []).reduce((n, e) => n + staleCount(e), 0);

  // the stale assumptions with the biggest dollar effect, across checked models
  const attention = useMemo(() => {
    const caseStudy = entries?.find((e) => e.report?.model_id === "case-study");
    if (!caseStudy) return [];
    return SAMPLE_TIMELINE.filter((ev) => ev.status === "stale" && ev.state && ev.impact.length)
      .map((ev) => ({
        ev,
        top: [...ev.impact].sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta))[0],
        entry: caseStudy,
      }))
      .sort((a, b) => Math.abs(b.top.delta) - Math.abs(a.top.delta))
      .slice(0, 3);
  }, [entries]);

  return (
    <div className="page home">
      <header className="bar home-bar">
        <Wordmark variant="plain" />
        <input
          className="home-search"
          type="search"
          placeholder="Search models"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search models"
        />
        <span className="bar-spacer" />
        <ImportButton onImport={onImport} />
        <Account />
      </header>

      <main className="home-main">
        {attention.length > 0 && (
          <section className="attention" aria-labelledby="attention-h">
            <div className="attention-head">
              <h2 id="attention-h">Needs attention</h2>
              <span className="mono muted">
                <span className="stale-text">{stale}</span> stale across {entries?.filter((e) => e.report).length} checked model
                {entries && entries.filter((e) => e.report).length === 1 ? "" : "s"}
              </span>
            </div>
            <div className="attention-row">
              {attention.map(({ ev, top, entry }) => (
                <button key={ev.id} className="attn-card" onClick={() => onOpen(entry, ev.id)}>
                  <span className="attn-label">{ev.state!.label}</span>
                  <span className="attn-values mono">
                    <span className="input">{value(ev.state!.model, ev.state!.unit)}</span>
                    <span className="muted">→</span>
                    <span>{ev.state!.live != null ? value(ev.state!.live, ev.state!.unit) : "—"}</span>
                    <span className="stale-text">{ev.state!.change}</span>
                  </span>
                  <span className="attn-effect mono">{deltaMoney(top.delta)}</span>
                  <span className="attn-meta mono muted">
                    {top.label} · {ev.cells[0]} · {title(entry.filename)}
                  </span>
                </button>
              ))}
            </div>
          </section>
        )}

        <section aria-labelledby="models-h">
          <div className="models-head">
            <h2 id="models-h">Models</h2>
            <span className="bar-spacer" />
            <div className="seg" role="group" aria-label="Layout">
              <button aria-pressed={layout === "grid"} onClick={() => setLayout("grid")}>
                Grid
              </button>
              <button aria-pressed={layout === "list"} onClick={() => setLayout("list")}>
                List
              </button>
            </div>
          </div>

          {entries === null ? (
            <p className="hint">Loading models…</p>
          ) : layout === "grid" ? (
            <div className="model-grid">
              <button className="model-card add-card" onClick={() => file.current?.click()}>
                <span className="add-plus" aria-hidden>
                  +
                </span>
                <span>Import .xlsx</span>
                <span className="muted small">or drop a file anywhere</span>
              </button>
              {shown.map((e) => (
                <article key={e.key} className="model-card">
                  <button className="card-open" onClick={() => onOpen(e)} aria-label={`Open ${e.filename}`}>
                    <SheetThumb book={e.book} report={e.report} />
                    <span className="card-foot">
                      <span className="card-icon" aria-hidden>
                        <Table size={14} strokeWidth={1.75} absoluteStrokeWidth />
                      </span>
                      <span className="card-name">{title(e.filename)}</span>
                      <span className="card-meta mono">
                        {e.report ? (
                          <>
                            {staleCount(e) > 0 ? <span className="stale-text">{staleCount(e)} stale</span> : "all current"} · set {e.builtOn}
                          </>
                        ) : (
                          <>imported {e.added ? shortDate(e.added.slice(0, 10)) : ""} · not checked</>
                        )}
                      </span>
                    </span>
                  </button>
                  {!e.report && (
                    <button className="card-remove" onClick={() => onRemove(e)} aria-label={`Remove ${e.filename}`}>
                      ×
                    </button>
                  )}
                </article>
              ))}
            </div>
          ) : (
            <table className="model-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th className="mt-status">Status</th>
                  <th className="mt-num">Constants</th>
                  <th className="mt-date">Last edited</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((e) => {
                  const n = staleCount(e);
                  return (
                    <tr key={e.key} onClick={() => onOpen(e)} tabIndex={0} onKeyDown={(k) => k.key === "Enter" && onOpen(e)}>
                      <td>
                        <span className="mt-name">
                          <span className="card-icon" aria-hidden>
                            <Table size={14} strokeWidth={1.75} absoluteStrokeWidth />
                          </span>
                          <span className="mt-title">{title(e.filename)}</span>
                          <span className="mt-sub mono">{e.report ? `assumptions set ${e.builtOn ? shortDate(e.builtOn) : "—"}` : e.filename}</span>
                          {!e.report && (
                            <button
                              className="mt-remove"
                              onClick={(ev) => {
                                ev.stopPropagation();
                                onRemove(e);
                              }}
                              aria-label={`Remove ${e.filename}`}
                            >
                              ×
                            </button>
                          )}
                        </span>
                      </td>
                      <td className="mt-status">
                        {!e.report ? (
                          <span className="mt-pill">Not checked</span>
                        ) : n ? (
                          <span className="mt-pill stale">{n} stale</span>
                        ) : (
                          <span className="mt-pill fresh">All current</span>
                        )}
                      </td>
                      <td className="mt-num mono">{e.report ? e.report.constants.length : <span className="muted">—</span>}</td>
                      <td className="mt-date" title={e.edited ? new Date(e.edited).toLocaleString() : undefined}>
                        {e.edited ? editedAt(e.edited) : <span className="muted">—</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
          {entries !== null && shown.length === 0 && query && <p className="hint">No models match “{query}”.</p>}
        </section>
      </main>

      <input
        ref={file}
        type="file"
        accept=".xlsx,.xlsm,.xls"
        hidden
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onImport(f);
          e.target.value = "";
        }}
      />
    </div>
  );
}

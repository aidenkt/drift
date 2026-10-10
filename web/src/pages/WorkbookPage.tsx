import { useEffect, useMemo, useState, type CSSProperties, type PointerEvent } from "react";
import EventDetail from "../components/EventDetail";
import DocBar from "../components/DocBar";
import { Panel } from "../components/icons";
import Spreadsheet, { type CellChange } from "../components/Spreadsheet";
import Timeline from "../components/Timeline";
import { SAMPLE_TIMELINE, type TimelineEvent } from "../data/timeline";
import { normalizeRef, rawRef, syncSheets, writeRef, type Book, type CellUpdate } from "../lib/workbook";
import type { Constant, Report } from "../types";

export type OpenModel = {
  id: number;
  filename: string;
  builtOn: string | null;
  book: Book;
  report: Report | null;
  startEvent?: string; // open with this change selected
};

type Props = {
  model: OpenModel;
  onImport: (file: File) => void;
  onBack: () => void;
  /** Any cell edit, so the home page can show when the model was last edited. */
  onEdited?: () => void;
};

const PANEL = { timeline: 320, detail: 380 };
const LIMITS = { timeline: [240, 560], detail: [300, 640] } as const;
const SHEET_MIN = 360;
const stored = (key: keyof typeof PANEL) => {
  const n = Number(localStorage.getItem(`since.panel.${key}`));
  return n ? clamp(n, LIMITS[key][0], LIMITS[key][1]) : PANEL[key];
};
const clamp = (n: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, n));

export default function WorkbookPage({ model, onImport, onBack, onEdited }: Props) {
  // browser tab: "Since · case_study_aug2026", back to "Since" on the home page
  useEffect(() => {
    document.title = `Since · ${model.filename.replace(/\.(xlsx|xlsm|xls)$/i, "")}`;
    return () => {
      document.title = "Since";
    };
  }, [model.filename]);

  // cells updated to their live value from the inspector stop being stale
  const [updated, setUpdated] = useState<Set<string>>(new Set());
  const constants = useMemo(() => {
    const map = new Map<string, Constant>();
    for (const c of model.report?.constants ?? []) {
      const key = normalizeRef(c.cell);
      const done = updated.has(key) && c.check;
      map.set(key, done ? { ...c, check: { ...c.check!, status: "current" } } : c);
    }
    return map;
  }, [model.report, updated]);
  const stale = [...constants.values()].filter((c) => c.check?.status === "stale").length;

  // The case study gets the sample timeline until the engine produces one.
  const sample = model.report?.model_id === "case-study";
  const [edits, setEdits] = useState<TimelineEvent[]>([]);
  const events = useMemo(() => [...edits, ...(sample ? SAMPLE_TIMELINE : [])], [edits, sample]);

  const [openId, setOpenId] = useState<string | null>(model.startEvent ?? null);
  const [showChanges, setShowChanges] = useState(true);
  const [widths, setWidths] = useState(() => ({ timeline: stored("timeline"), detail: stored("detail") }));
  const [resizing, setResizing] = useState(false);
  useEffect(() => {
    localStorage.setItem("since.panel.timeline", String(widths.timeline));
    localStorage.setItem("since.panel.detail", String(widths.detail));
  }, [widths]);

  /** Drag a divider. "edge" is the panel's left edge; "split" sits between the list and the open change. */
  const startResize = (e: PointerEvent<HTMLDivElement>, which: "edge" | "split") => {
    if (e.button !== 0) return;
    e.preventDefault();
    const handle = e.currentTarget;
    handle.setPointerCapture(e.pointerId);
    const x0 = e.clientX;
    const start = widths;
    const inspecting = !!openEvent;
    const room = window.innerWidth - SHEET_MIN; // keep the sheet usable
    setResizing(true);
    const onMove = (ev: globalThis.PointerEvent) => {
      const dx = ev.clientX - x0;
      setWidths(() => {
        if (which === "split") {
          const timeline = clamp(start.timeline + dx, LIMITS.timeline[0], Math.min(LIMITS.timeline[1], start.timeline + start.detail - LIMITS.detail[0]));
          return { timeline, detail: clamp(start.detail - (timeline - start.timeline), ...LIMITS.detail) };
        }
        // the left edge grows the panel; with a change open, the open change takes the extra width
        if (inspecting) {
          const detail = clamp(start.detail - dx, LIMITS.detail[0], Math.min(LIMITS.detail[1], room - start.timeline));
          return { ...start, detail };
        }
        return { ...start, timeline: clamp(start.timeline - dx, LIMITS.timeline[0], Math.min(LIMITS.timeline[1], room)) };
      });
    };
    const onUp = () => {
      setResizing(false);
      handle.removeEventListener("pointermove", onMove);
      handle.removeEventListener("pointerup", onUp);
      handle.removeEventListener("pointercancel", onUp);
    };
    handle.addEventListener("pointermove", onMove);
    handle.addEventListener("pointerup", onUp);
    handle.addEventListener("pointercancel", onUp);
  };
  const resetWidth = (which: "edge" | "split") =>
    setWidths((w) => (which === "split" || openEvent ? { ...w, timeline: PANEL.timeline, detail: PANEL.detail } : { ...w, timeline: PANEL.timeline }));
  const [rev, setRev] = useState(0);
  const history = (redo: boolean) => {
    const hf = model.book.hf;
    if (redo ? hf.isThereSomethingToRedo() : hf.isThereSomethingToUndo()) {
      redo ? hf.redo() : hf.undo();
      syncSheets(model.book);
      setRev((r) => r + 1);
    }
  };
  const [focus, setFocus] = useState<{ ref: string; nonce: number } | null>(() => {
    const cell = events.find((e) => e.id === model.startEvent)?.cells[0];
    return cell ? { ref: cell, nonce: 0 } : null;
  });
  const openEvent = events.find((e) => e.id === openId) ?? null;
  const [cellEventId, setCellEventId] = useState<string | null>(null);
  // the last opened change stays rendered while the inspector slides shut
  const [shown, setShown] = useState<TimelineEvent | null>(null);
  useEffect(() => {
    if (openEvent) setShown(openEvent);
  }, [openEvent]);
  const toggleChanges = () => {
    if (showChanges) setOpenId(null);
    setShowChanges((v) => !v);
  };

  // opening a change keeps the sheet in view and moves the selection to its cell
  const select = (id: string) => {
    const cell = events.find((e) => e.id === id)?.cells[0];
    setOpenId(id);
    setCellEventId(id);
    if (cell) setFocus({ ref: cell, nonce: Date.now() });
  };
  const close = () => setOpenId(null);

  // clicking a cell picks out its latest change in the list; an open change follows along
  const onSelectCell = (ref: string) => {
    const key = normalizeRef(ref);
    if (openEvent?.cells.some((c) => normalizeRef(c) === key)) return;
    const hit = events.find((e) => e.kind !== "baseline" && e.cells.some((c) => normalizeRef(c) === key));
    setCellEventId(hit?.id ?? null);
    if (hit && openId) setOpenId(hit.id);
  };
  const showCell = (ref: string) => setFocus({ ref, nonce: Date.now() });

  useEffect(() => {
    if (!openId) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [openId]);

  const apply = (event: TimelineEvent, updates: CellUpdate[]) => {
    const cell = event.cells[0];
    const before = rawRef(model.book, cell);
    model.book.hf.batch(() => updates.forEach((u) => writeRef(model.book, u.cell, u.text)));
    setRev((r) => r + 1);
    setUpdated((prev) => new Set(prev).add(normalizeRef(cell)));
    onEdit([{ ref: cell, before, after: rawRef(model.book, cell) }]);
  };

  /** moved: how many cells a cut-and-paste carried (its changes also list the emptied source). */
  const onEdit = (changes: CellChange[], moved?: number) => {
    if (!changes.length) return;
    const { ref, before, after } = changes[0];
    const many = changes.length > 1;
    const label = constants.get(normalizeRef(ref))?.label;
    const today = new Date().toISOString().slice(0, 10);
    const cleared = changes.every((c) => c.after === "");
    const title = moved
      ? `${moved} ${moved === 1 ? "cell" : "cells"} moved`
      : many
        ? `${changes.length} cells ${cleared ? "cleared" : "pasted"}`
      : after === ""
        ? `${label ?? ref} cleared`
        : `${label ?? ref} set to ${after}`;
    const event: TimelineEvent = {
      id: `edit-${Date.now()}`,
      date: today,
      at: new Date().toISOString(),
      by: "You",
      title,
      kind: "edit",
      status: "edited",
      cells: changes.map((c) => c.ref),
      driver: null,
      signals: [],
      sources: [],
      impact: [],
      // a multi-cell change lists its cells; before/after only reads well for one
      edit: many ? undefined : { before, after },
    };
    setEdits((prev) => [event, ...prev]);
    onEdited?.();
  };

  return (
    <div className="page workbook">
      <DocBar
        filename={model.filename}
        builtOn={model.builtOn}
        stale={model.report ? stale : null}
        total={model.report?.constants.length ?? 0}
        showChanges={showChanges}
        onToggleChanges={toggleChanges}
        onUndo={() => history(false)}
        onRedo={() => history(true)}
        onImport={onImport}
        onHome={onBack}
      />

      <div
        className={`workspace${resizing ? " resizing" : ""}`}
        style={{ "--timeline-w": `${widths.timeline}px`, "--detail-w": `${widths.detail}px` } as CSSProperties}
      >
        <div className="workspace-sheet">
          <Spreadsheet
            book={model.book}
            constants={constants}
            focus={focus}
            onEdit={onEdit}
            onSelectCell={onSelectCell}
            rev={rev}
            toolbarEnd={
              <button
                className={`tb-btn tb-text ${showChanges ? "on" : ""}`}
                aria-pressed={showChanges}
                onClick={toggleChanges}
              >
                <Panel />
                Changes
              </button>
            }
          />
        </div>
        {/* slides in from the right; opening a change widens it, the list stays on its left */}
        <div className={`sidebar ${showChanges ? "open" : ""} ${openEvent ? "inspecting" : ""}`} inert={!showChanges}>
          <div
            className="panel-resize edge"
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize changes panel"
            onPointerDown={(e) => startResize(e, "edge")}
            onDoubleClick={() => resetWidth("edge")}
          />
          {openEvent && (
            <div
              className="panel-resize split"
              role="separator"
              aria-orientation="vertical"
              aria-label="Resize change details"
              onPointerDown={(e) => startResize(e, "split")}
              onDoubleClick={() => resetWidth("split")}
            />
          )}
          <Timeline events={events} selectedId={openId ?? cellEventId} onSelect={select} />
          <div className="sidebar-detail" inert={!openEvent}>
            {shown && (
              <EventDetail
                event={shown}
                book={model.book}
                rev={rev}
                applied={shown.cells.length === 1 && updated.has(normalizeRef(shown.cells[0]))}
                onShowCell={showCell}
                onApply={apply}
                onClose={close}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

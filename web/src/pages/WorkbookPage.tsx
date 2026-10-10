import { useEffect, useMemo, useState } from "react";
import { flushSync } from "react-dom";
import EventDetail from "../components/EventDetail";
import DocBar from "../components/DocBar";
import { Panel } from "../components/icons";
import Spreadsheet from "../components/Spreadsheet";
import Timeline from "../components/Timeline";
import { SAMPLE_TIMELINE, type TimelineEvent } from "../data/timeline";
import { normalizeRef, type Book } from "../lib/workbook";
import type { Constant, Report } from "../types";

export type OpenModel = { id: number; filename: string; builtOn: string | null; book: Book; report: Report | null };

type Props = { model: OpenModel; onImport: (file: File) => void; onBack: () => void };

/** Animate the layout swap where supported; the timeline slides between sides. */
function transition(update: () => void) {
  const doc = document as Document & { startViewTransition?: (cb: () => void) => unknown };
  if (doc.startViewTransition && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
    doc.startViewTransition(() => flushSync(update));
  } else {
    update();
  }
}

export default function WorkbookPage({ model, onImport, onBack }: Props) {
  const constants = useMemo(
    () => new Map<string, Constant>((model.report?.constants ?? []).map((c) => [normalizeRef(c.cell), c])),
    [model.report],
  );
  const stale = model.report?.constants.filter((c) => c.check?.status === "stale").length ?? 0;

  // The case study gets the sample timeline until the engine produces one.
  const sample = model.report?.model_id === "case-study";
  const [edits, setEdits] = useState<TimelineEvent[]>([]);
  const events = useMemo(() => [...edits, ...(sample ? SAMPLE_TIMELINE : [])], [edits, sample]);

  const [openId, setOpenId] = useState<string | null>(null);
  const [showChanges, setShowChanges] = useState(true);
  const [rev, setRev] = useState(0);
  const history = (redo: boolean) => {
    const hf = model.book.hf;
    if (redo ? hf.isThereSomethingToRedo() : hf.isThereSomethingToUndo()) {
      redo ? hf.redo() : hf.undo();
      setRev((r) => r + 1);
    }
  };
  const [focus, setFocus] = useState<{ ref: string; nonce: number } | null>(null);
  const openEvent = events.find((e) => e.id === openId) ?? null;

  const select = (id: string) => transition(() => setOpenId(id));
  const close = () => transition(() => setOpenId(null));
  // both inside the transition, so the grid is visible by the time it takes focus
  const showCell = (ref: string) =>
    transition(() => {
      setOpenId(null);
      setFocus({ ref, nonce: Date.now() });
    });

  useEffect(() => {
    if (!openId) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [openId]);

  const onEdit = (ref: string, before: string, after: string) => {
    const label = constants.get(normalizeRef(ref))?.label;
    const today = new Date().toISOString().slice(0, 10);
    const event: TimelineEvent = {
      id: `edit-${Date.now()}`,
      date: today,
      title: after === "" ? `${label ?? ref} cleared` : `${label ?? ref} set to ${after}`,
      kind: "edit",
      status: "edited",
      cells: [ref],
      driver: null,
      signals: [],
      sources: [],
      impact: [],
      edit: { before, after },
    };
    setEdits((prev) => [event, ...prev]);
  };

  return (
    <div className="page workbook">
      <DocBar
        filename={model.filename}
        builtOn={model.builtOn}
        stale={model.report ? stale : null}
        total={model.report?.constants.length ?? 0}
        showChanges={showChanges}
        onToggleChanges={() => transition(() => setShowChanges((v) => !v))}
        onUndo={() => history(false)}
        onRedo={() => history(true)}
        onImport={onImport}
        onHome={onBack}
      />

      <div className={`workspace ${openEvent ? "expanded" : ""} ${showChanges || openEvent ? "" : "no-changes"}`}>
        {/* stays mounted so selection, sheet and edits survive opening an event */}
        <div className="workspace-sheet" hidden={!!openEvent}>
          <Spreadsheet
            book={model.book}
            constants={constants}
            focus={focus}
            onEdit={onEdit}
            rev={rev}
            toolbarEnd={
              <button
                className={`tb-btn tb-text ${showChanges ? "on" : ""}`}
                aria-pressed={showChanges}
                onClick={() => transition(() => setShowChanges((v) => !v))}
              >
                <Panel />
                Changes
              </button>
            }
          />
        </div>
        {(showChanges || openEvent) && <Timeline events={events} selectedId={openId} onSelect={select} sample={sample} />}
        {openEvent && <EventDetail event={openEvent} onShowCell={showCell} onClose={close} />}
      </div>
    </div>
  );
}

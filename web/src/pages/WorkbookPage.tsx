import { useEffect, useMemo, useRef, useState, type CSSProperties, type PointerEvent } from "react";
import EventDetail from "../components/EventDetail";
import DocBar from "../components/DocBar";
import Presence from "../components/Presence";
import ShareDialog from "../components/ShareDialog";
import { Panel } from "../components/icons";
import Spreadsheet, { type CellChange } from "../components/Spreadsheet";
import Timeline, { reviewOrder } from "../components/Timeline";
import { SAMPLE_TIMELINE, type TimelineEvent } from "../data/timeline";
import { colorFor, createShared, joinPresence, me, saveShared, signedIn, type Me, type Person, type SharedDoc } from "../lib/collab";
import { apply as applyCells, diff, snapshot, type CellsOp } from "../lib/live";
import { downloadXlsx, normalizeRef, rawRef, syncSheets, writeRef, xlsxBytes, xlsxName, type Book, type CellUpdate } from "../lib/workbook";
import { value } from "../lib/format";
import { assess } from "../lib/resolve";
import { eventsFromReport } from "../lib/reportTimeline";
import type { Constant, Report } from "../types";

export type OpenModel = {
  id: number;
  filename: string;
  builtOn: string | null;
  book: Book;
  report: Report | null;
  startEvent?: string; // open with this change selected
  startCell?: string; // or on this cell, e.g. from the path after a reload
  doc?: SharedDoc; // set once the workbook is shared through the engine
};

type Props = {
  model: OpenModel;
  onImport: (file: File) => void;
  onBack: () => void;
  onRename: (name: string) => void;
  onNew: () => void;
  onCopy: () => void;
  /** Only for files kept in this browser; checked and shared models can't be trashed from here. */
  onTrash?: () => void;
  /** The active cell ("P&L!C18") whenever it moves, so the path can follow it. */
  onCell?: (cell: string) => void;
  /** Any cell edit, so the home page can show when the model was last edited. */
  onEdited?: () => void;
  /** The workbook was uploaded for sharing, or its access list changed. */
  onShared?: (doc: SharedDoc) => void;
  /** Signed in, upload to Base44 as soon as it opens (imports, new sheets) rather than on the
   *  first edit (checked models everyone sees, so looking at one doesn't make a copy). */
  uploadOnOpen?: boolean;
};

const PANEL = { timeline: 320 };
const LIMITS = { timeline: [240, 560] } as const;
const SHEET_MIN = 360;
// an open change takes this share of the width, so a strip of sheet stays visible to click back to
const OPEN = { default: 0.95, max: 0.95, detailMin: 420 };
const stored = (key: keyof typeof PANEL) => {
  const n = Number(localStorage.getItem(`since.panel.${key}`));
  return n ? clamp(n, LIMITS[key][0], LIMITS[key][1]) : PANEL[key];
};
const clamp = (n: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, n));

export default function WorkbookPage({ model, onImport, onBack, onRename, onNew, onCopy, onTrash, onCell, onEdited, onShared, uploadOnOpen }: Props) {
  // browser tab: "Since · case_study_aug2026", back to "Since" on the home page
  useEffect(() => {
    document.title = `Since · ${model.filename.replace(/\.(xlsx|xlsm|xls)$/i, "")}`;
    return () => {
      document.title = "Since";
    };
  }, [model.filename]);

  // The case study keeps the sample timeline; any other report is read as the engine wrote it.
  const sample = model.report?.model_id === "case-study";
  const checked = useMemo(() => (sample ? SAMPLE_TIMELINE : model.report ? eventsFromReport(model.report) : []), [sample, model.report]);
  const [edits, setEdits] = useState<TimelineEvent[]>([]);
  const [rev, setRev] = useState(0);

  /* ---------- stale assumptions: still stale, updated, kept on purpose, or gone ---------- */
  // "Keep as is" is a choice, so it's remembered; everything else is read off the cell itself
  const [kept, setKept] = useState<Map<string, string>>(new Map()); // event id -> when
  // the last edit to each stale assumption's cell: it resolves that entry instead of adding a row
  const [touched, setTouched] = useState<Map<string, { at: string; by: string }>>(new Map());
  const events = useMemo(() => {
    const checks = checked.map((e): TimelineEvent => {
      if (e.status !== "stale" || !e.state) return e;
      const who = touched.get(e.id);
      if (kept.has(e.id))
        return { ...e, status: "kept", resolution: { note: `Kept at ${value(e.state.model, e.state.unit)}`, at: kept.get(e.id), by: "You" } };
      const o = assess(model.book, e);
      if (o.status === "updated") return { ...e, status: "updated", resolution: { note: `Updated to ${value(o.now, e.state.unit)}`, ...who } };
      if (o.status === "gone") return { ...e, status: "gone", resolution: { note: o.note, ...who } };
      return o.note ? { ...e, resolution: { note: o.note, ...who } } : e;
    });
    return [...edits, ...checks];
    // rev: re-read the cells after edits, updates and undo
  }, [edits, checked, kept, touched, rev, model.book]);

  // a resolved assumption's cell stops being flagged in the grid and the stale count
  const constants = useMemo(() => {
    const resolved = new Set(
      events.filter((e) => ["updated", "kept", "gone"].includes(e.status)).flatMap((e) => e.cells.map(normalizeRef)),
    );
    const map = new Map<string, Constant>();
    // two numbers in one formula share a cell: the checked one shows, a stale one first
    const rank = (c: Constant) => (c.check?.status === "stale" ? 2 : c.check ? 1 : 0);
    for (const c of model.report?.constants ?? []) {
      // a number copied across a row is one constant, flagged in every cell that holds it
      for (const cell of c.cells ?? [c.cell]) {
        const key = normalizeRef(cell);
        const prev = map.get(key);
        if (prev && rank(prev) > rank(c)) continue;
        map.set(key, resolved.has(key) && c.check ? { ...c, check: { ...c.check, status: "current" } } : c);
      }
    }
    return map;
  }, [model.report, events]);
  // counted once each, however many cells a constant covers
  const stale = new Set([...constants.values()].filter((c) => c.check?.status === "stale").map((c) => `${c.cell}#${c.literal_index}`)).size;

  const setKeep = (id: string, at: string | null) =>
    setKept((prev) => {
      const next = new Map(prev);
      if (at) next.set(id, at);
      else next.delete(id);
      return next;
    });
  const keep = (e: TimelineEvent, on: boolean) => {
    const at = on ? new Date().toISOString() : null;
    setKeep(e.id, at);
    send({ kept: { id: e.id, at } });
    if (on) advance(e.id);
  };

  // after a stale change is dealt with, open the next one down the list; none left closes the change
  const advance = (fromId: string) => {
    const order = reviewOrder(events);
    const at = order.findIndex((e) => e.id === fromId);
    const next = [...order.slice(at + 1), ...order.slice(0, Math.max(at, 0))].find((e) => e.id !== fromId);
    if (next) select(next.id);
    else close();
  };

  const [openId, setOpenId] = useState<string | null>(model.startEvent ?? null);
  const [showChanges, setShowChanges] = useState(true);
  const [widths, setWidths] = useState(() => ({ timeline: stored("timeline") }));
  const [openShare, setOpenShare] = useState(() => clamp(Number(localStorage.getItem("since.panel.open")) || OPEN.default, 0.3, OPEN.max));
  const [resizing, setResizing] = useState(false);
  useEffect(() => {
    localStorage.setItem("since.panel.timeline", String(widths.timeline));
    localStorage.setItem("since.panel.open", String(openShare));
  }, [widths, openShare]);

  /** Drag the panel's left edge: the list's width, or with a change open, the whole panel's share. */
  const startResize = (e: PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    e.preventDefault();
    const handle = e.currentTarget;
    handle.setPointerCapture(e.pointerId);
    const x0 = e.clientX;
    const start = widths;
    const room = window.innerWidth - SHEET_MIN; // keep the sheet usable
    const total = handle.closest(".workspace")!.getBoundingClientRect().width;
    const panel0 = handle.parentElement!.getBoundingClientRect().width;
    const inspecting = !!openEvent;
    setResizing(true);
    const onMove = (ev: globalThis.PointerEvent) => {
      const dx = ev.clientX - x0;
      if (inspecting) setOpenShare(clamp((panel0 - dx) / total, Math.min(OPEN.max, (start.timeline + OPEN.detailMin) / total), OPEN.max));
      else setWidths({ timeline: clamp(start.timeline - dx, LIMITS.timeline[0], Math.min(LIMITS.timeline[1], room)) });
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
  const resetWidth = () => (openEvent ? setOpenShare(OPEN.default) : setWidths({ timeline: PANEL.timeline }));

  /* ---------- sharing and presence ---------- */
  const [doc, setDoc] = useState<SharedDoc | null>(model.doc ?? null);
  const [sharing, setSharing] = useState(false);
  const [people, setPeople] = useState<Person[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const room = useRef<ReturnType<typeof joinPresence> | null>(null);
  const canSave = doc?.role === "owner" || doc?.role === "editor";

  const updateDoc = (next: SharedDoc) => {
    setDoc(next);
    onShared?.(next);
  };
  // the first invite uploads the workbook as it is now
  // the first upload, kept so opening, sharing and React's double effects all wait on the same one
  const creating = useRef<Promise<SharedDoc> | null>(null);
  const ensureDoc = async () =>
    doc ?? (creating.current ??= createShared(xlsxBytes(model.book), xlsxName(model.filename)).then((d) => (updateDoc(d), d)));
  // signed in, every workbook lives on Base44: one that isn't there yet is uploaded, and from
  // then on it saves, syncs and shows on every device like a shared one
  const upload = () => {
    if (signedIn() && !doc) ensureDoc().catch((e) => setNotice(`Couldn't save to Base44: ${e.message}`));
  };
  useEffect(() => void (uploadOnOpen && upload()), []);

  /* ---------- live edits: what changed in the cells goes to everyone with the workbook open ---------- */
  type Op = { cells?: CellsOp; event?: TimelineEvent; kept?: { id: string; at: string | null }; touched?: { id: string; at: string }; filename?: string };
  const send = (op: Op) => room.current?.send(op);
  const live = useRef<{ snap: ReturnType<typeof snapshot> | null; applying: boolean; timer?: number }>({ snap: null, applying: false });
  const dirty = useRef(false); // changed here since the last save; others' edits are theirs to save
  const flush = () => {
    const l = live.current;
    clearTimeout(l.timer);
    l.timer = undefined;
    if (!l.snap) return;
    const next = snapshot(model.book);
    const cells = diff(l.snap, next);
    l.snap = next;
    if (cells) {
      dirty.current = true;
      send({ cells });
    }
  };
  const pushCells = () => {
    const l = live.current;
    if (l.applying || !l.snap) return;
    clearTimeout(l.timer);
    l.timer = window.setTimeout(flush, 80);
  };
  const receive = useRef<(op: Op, by: Me) => void>(() => {});
  receive.current = (op, by) => {
    if (op.cells) {
      if (live.current.timer) flush(); // ours go out first, or the snapshot below would swallow them
      live.current.applying = true;
      try {
        applyCells(model.book, op.cells);
      } finally {
        live.current.applying = false;
      }
      live.current.snap = snapshot(model.book);
      setRev((r) => r + 1);
    }
    if (op.event) {
      const ev = { ...op.event, by: by.name };
      setEdits((prev) => (prev.some((e) => e.id === ev.id) ? prev : [ev, ...prev]));
    }
    if (op.kept) setKeep(op.kept.id, op.kept.at);
    if (op.touched) setTouched((prev) => new Map(prev).set(op.touched!.id, { at: op.touched!.at, by: by.name }));
    // renamed by someone else: Base44 already has it, so only the title changes here
    if (op.filename && doc) updateDoc({ ...doc, filename: op.filename });
  };

  useEffect(() => {
    if (!doc) return;
    const r = joinPresence(doc.doc_id, {
      onPeople: setPeople,
      onOp: (op, by) => receive.current(op as Op, by),
      onError: setNotice,
    });
    room.current = r;
    live.current.snap = snapshot(model.book);
    // any change to the cells, from typing, pasting, undo or a new sheet
    const hf = model.book.hf;
    const events = ["valuesUpdated", "sheetAdded", "sheetRemoved", "sheetRenamed"] as const;
    events.forEach((e) => hf.on(e, pushCells));
    return () => {
      events.forEach((e) => hf.off(e, pushCells));
      clearTimeout(live.current.timer);
      live.current.snap = null;
      r.close();
      room.current = null;
      setPeople([]);
    };
  }, [doc?.doc_id, model.book]);
  // edits that don't change a value (a formula with the same result, a number format) still count
  useEffect(() => pushCells(), [rev, edits]);
  // the first change to a workbook that isn't on Base44 yet puts it there
  const opened = useRef({ rev, edits, kept, touched });
  useEffect(() => {
    const o = opened.current;
    if (o.rev !== rev || o.edits !== edits || o.kept !== kept || o.touched !== touched) upload();
  }, [rev, edits, kept, touched]);
  const history = (redo: boolean) => {
    const hf = model.book.hf;
    if (redo ? hf.isThereSomethingToRedo() : hf.isThereSomethingToUndo()) {
      redo ? hf.redo() : hf.undo();
      syncSheets(model.book);
      setRev((r) => r + 1);
    }
  };
  const [focus, setFocus] = useState<{ ref: string; nonce: number } | null>(() => {
    const cell = events.find((e) => e.id === model.startEvent)?.cells[0] ?? model.startCell;
    return cell ? { ref: cell, nonce: 0 } : null;
  });
  const openEvent = events.find((e) => e.id === openId) ?? null;
  const [cellEventId, setCellEventId] = useState<string | null>(null);
  // the last opened change stays rendered while the inspector slides shut
  const [shown, setShown] = useState<TimelineEvent | null>(null);
  useEffect(() => {
    if (openEvent) setShown(openEvent);
  }, [openEvent]);
  const shownLive = shown ? (events.find((e) => e.id === shown.id) ?? shown) : null;
  const toggleChanges = () => {
    if (showChanges) setOpenId(null);
    setShowChanges((v) => !v);
  };

  // opening a change moves the selection to its cell, so closing it lands there
  const select = (id: string) => {
    const cell = events.find((e) => e.id === id)?.cells[0];
    setOpenId(id);
    setCellEventId(id);
    if (cell) setFocus({ ref: cell, nonce: Date.now() });
  };
  const close = () => setOpenId(null);
  // a cell chip in the open change closes it to show that cell in the sheet
  const closeToCell = (ref: string) => {
    close();
    showCell(ref);
  };

  // clicking a cell picks out its latest change in the list; an open change follows along
  // shared workbooks save themselves a moment after each change, for editors and the owner
  useEffect(() => {
    if (!doc || !canSave) return;
    const t = window.setTimeout(() => {
      if (!dirty.current) return;
      dirty.current = false;
      saveShared(doc.doc_id, xlsxBytes(model.book))
        .then(() => room.current?.saved())
        .catch((e) => setNotice(`Couldn't save: ${e.message}`));
    }, 1500);
    return () => clearTimeout(t);
  }, [rev, edits, doc, canSave]);

  const [here, setHere] = useState<{ cell: string | null; range: string | null }>({ cell: null, range: null });
  useEffect(() => room.current?.setHere({ ...here, open: openId }), [here, openId, people.length]);
  const onSelectCell = (ref: string, range?: string) => {
    setHere({ cell: ref, range: range ?? null });
    onCell?.(ref);
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

  const download = () => downloadXlsx(model.book, model.filename);
  // ⌘S / Ctrl+S saves a copy instead of the browser's "save page"; ⌘O goes to all models, as File › Open
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        downloadXlsx(model.book, model.filename);
      }
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "o") {
        e.preventDefault();
        onBack();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [model]);

  const apply = (event: TimelineEvent, updates: CellUpdate[]) => {
    const cell = event.cells[0];
    const before = rawRef(model.book, cell);
    model.book.hf.batch(() => updates.forEach((u) => writeRef(model.book, u.cell, u.text)));
    setRev((r) => r + 1);
    onEdit([{ ref: cell, before, after: rawRef(model.book, cell) }]);
    advance(event.id);
  };

  /** moved: how many cells a cut-and-paste carried (its changes also list the emptied source).
   *  title: set for edits that aren't cell writes, like inserting rows. */
  const onEdit = (changes: CellChange[], moved?: number, title?: string) => {
    if (!changes.length) return;
    const { ref, before, after } = changes[0];
    const many = changes.length > 1;

    // editing a stale assumption's cell resolves (or re-checks) that entry rather than adding one;
    // with no live value to compare against there's nothing to resolve, so the edit is logged as usual
    const check = !many && !moved && !title && checked.find((e) => e.status === "stale" && e.state?.live != null && e.cells.some((c) => normalizeRef(c) === normalizeRef(ref)));
    if (check) {
      const at = new Date().toISOString();
      setTouched((prev) => new Map(prev).set(check.id, { at, by: "You" }));
      send({ touched: { id: check.id, at } });
      setKept((prev) => (prev.has(check.id) ? new Map([...prev].filter(([id]) => id !== check.id)) : prev));
      setRev((r) => r + 1);
      onEdited?.();
      return;
    }
    const label = constants.get(normalizeRef(ref))?.label;
    const today = new Date().toISOString().slice(0, 10);
    const cleared = changes.every((c) => c.after === "");
    const heading = title ?? (moved
      ? `${moved} ${moved === 1 ? "cell" : "cells"} moved`
      : many
        ? `${changes.length} cells ${cleared ? "cleared" : "pasted"}`
      : after === ""
        ? `${label ?? ref} cleared`
        : `${label ?? ref} set to ${after}`);
    const event: TimelineEvent = {
      id: `edit-${Date.now()}`,
      date: today,
      at: new Date().toISOString(),
      by: "You",
      title: heading,
      kind: "edit",
      status: "edited",
      cells: changes.map((c) => c.ref),
      driver: null,
      signals: [],
      sources: [],
      impact: [],
      // a multi-cell change lists its cells; before/after only reads well for one
      edit: many || title ? undefined : { before, after },
    };
    setEdits((prev) => [event, ...prev]);
    send({ event });
    onEdited?.();
  };

  // the others in the workbook, and which change each has open
  const others = people.filter((p) => p.email !== me().email);
  const viewers = useMemo(() => {
    const by = new Map<string, Person[]>();
    for (const p of others) if (p.open) by.set(p.open, [...(by.get(p.open) ?? []), p]);
    return by;
  }, [people]);
  const whereIs = (p: Person) => {
    const open = p.open && events.find((e) => e.id === p.open);
    return open ? open.title : (p.range ?? p.cell);
  };
  const jumpTo = (p: Person) => {
    if (p.open && events.some((e) => e.id === p.open)) return select(p.open);
    close();
    if (p.cell) showCell(p.cell);
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
        onDownload={download}
        onHome={onBack}
        onRename={(name) => {
          onRename(name);
          send({ filename: name + (model.filename.match(/\.(xlsx|xlsm|xls)$/i)?.[0] ?? ".xlsx") });
        }}
        onNew={onNew}
        onCopy={onCopy}
        onTrash={onTrash}
        onShare={() => setSharing(true)}
        presence={doc && people.length > 0 ? <Presence people={people} where={whereIs} onJump={jumpTo} /> : null}
      />
      {sharing && (
        <ShareDialog filename={model.filename} doc={doc} ensureDoc={ensureDoc} onChange={updateDoc} onClose={() => setSharing(false)} />
      )}
      {notice && (
        <div className="toast" role="status">
          {notice}
          <button onClick={() => setNotice(null)} aria-label="Dismiss">
            ×
          </button>
        </div>
      )}

      <div
        className={`workspace${resizing ? " resizing" : ""}`}
        style={{ "--timeline-w": `${widths.timeline}px`, "--open-w": `${openShare * 100}%` } as CSSProperties}
      >
        <div className="workspace-sheet">
          {/* the strip of sheet left beside an open change: clicking it closes the change */}
          {openEvent && <div className="sheet-scrim" onClick={close} aria-hidden />}
          <Spreadsheet
            book={model.book}
            constants={constants}
            focus={focus}
            onEdit={onEdit}
            onSelectCell={onSelectCell}
            onHistory={() => setRev((r) => r + 1)}
            peers={others
              .filter((p) => p.cell)
              .map((p) => ({ cell: p.cell!, range: p.range, color: colorFor(p.email), name: p.name }))}
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
        {/* the list, on the right; opening a change widens the panel over the whole sheet,
            the list keeps its column on the left and the change fills the rest */}
        <div className={`sidebar ${showChanges ? "open" : ""} ${openEvent ? "inspecting" : ""}`} inert={!showChanges}>
          <div
            className="panel-resize edge"
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize changes panel"
            onPointerDown={startResize}
            onDoubleClick={resetWidth}
          />
          <Timeline events={events} selectedId={openId ?? cellEventId} onSelect={select} viewers={viewers} />
          <div className="sidebar-detail" inert={!openEvent}>
            {shownLive && (
              <EventDetail
                event={shownLive}
                book={model.book}
                rev={rev}
                onShowCell={closeToCell}
                onApply={apply}
                onKeep={keep}
                onClose={close}
                viewers={viewers.get(shownLive.id) ?? []}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

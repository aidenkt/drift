import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type CSSProperties, type MouseEvent as ReactMouseEvent, type ReactNode } from "react";
import * as XLSX from "xlsx";
import type { Constant } from "../types";
import {
  addSheet,
  colName,
  FORMATS,
  getFormat,
  normalizeRef,
  parseRef,
  raw,
  ref,
  removeSheet,
  renameSheet,
  setFormat,
  shiftDecimals,
  shiftLines,
  syncSheets,
  view,
  write,
  type Book,
} from "../lib/workbook";
import { Chevron, DecLess, DecMore, Redo, Undo } from "./icons";
import Menu, { ContextMenu, type MenuItem } from "./Menu";
import ConstantStrip from "./ConstantStrip";
import { fromTsv, shiftFormula, toHtml, toTsv } from "../lib/clipboard";

const DEFAULT_COL = 96;
const ROW_HEAD = 44;
const PAD_ROWS = 30;
const PAD_COLS = 4;
const MOD = navigator.platform.includes("Mac") ? "⌘" : "Ctrl+";
const SHIFT = navigator.platform.includes("Mac") ? "⇧" : "Shift+";

type Edit = { text: string; from: "cell" | "bar" };
type Pos = { r: number; c: number };
/** What a mouse drag is extending: cells, or whole rows/columns from the headers. */
type Drag = "cell" | "row" | "col";
type Range = { r0: number; r1: number; c0: number; c1: number };
export type CellChange = { ref: string; before: string; after: string };
/** The last range copied or cut here; tsv is what went on the system clipboard, to recognise it on paste. */
type Clip = { sheetId: number; range: Range; cut: boolean; tsv: string };

type Props = {
  book: Book;
  constants: Map<string, Constant>;
  /** Jump to a cell; nonce lets the same ref be focused twice. */
  focus?: { ref: string; nonce: number } | null;
  /** Every write, one call per user action (a paste or a range clear arrives as one batch).
   *  Called with no changes for other steps undo can take back, like a new sheet. */
  onEdit?: (changes: CellChange[], moved?: number, title?: string) => void;
  /** The active cell, whenever it changes, and the highlighted range when it's more than one cell. */
  onSelectCell?: (ref: string, range?: string) => void;
  /** Bumped by the page after undo/redo from the menu bar, to re-render. */
  rev?: number;
  toolbarEnd?: ReactNode;
  /** Other people's active cells, outlined in their colour, and what they've highlighted, tinted. */
  peers?: { cell: string; range: string | null; color: string; name: string }[];
  /** Only the owner of a shared workbook may delete its sheets; editors can't. */
  canDeleteSheets?: boolean;
  /** After undo or redo from the keyboard or toolbar, so the page can re-read the cells and the list. */
  onHistory?: (redo: boolean) => void;
};

export default function Spreadsheet({ book, constants, focus, onEdit, onSelectCell, toolbarEnd, peers, onHistory, canDeleteSheets = true }: Props) {
  const [sheetIx, setSheetIx] = useState(0);
  // sel is the active cell; ext is the other corner of the highlighted range
  const [sel, setSel] = useState<Pos>({ r: 0, c: 0 });
  const [ext, setExt] = useState<Pos>({ r: 0, c: 0 });
  const [drag, setDrag] = useState<Drag | null>(null);
  const pointerRef = useRef({ x: 0, y: 0 });
  const [edit, setEdit] = useState<Edit | null>(null);
  const [version, setVersion] = useState(0);
  const [clip, setClip] = useState<Clip | null>(null);
  const gridRef = useRef<HTMLDivElement>(null);
  // right-click menu, and what was right-clicked: a cell, or a row/column header
  const [ctx, setCtx] = useState<{ x: number; y: number; kind: Drag } | null>(null);
  const closeCtx = useCallback(() => setCtx(null), []);
  const keepScroll = useRef(false);
  const valuesOnly = useRef(false);

  const [renaming, setRenaming] = useState<{ ix: number; text: string } | null>(null);
  // sheet options open above the tab bar, outside it, since the bar scrolls and would clip them
  const [tabMenu, setTabMenu] = useState<{ ix: number; left: number } | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!tabMenu) return;
    const close = (e: Event) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !(e.target as Element).closest(".tab-pop, .tab-more")) setTabMenu(null);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [tabMenu]);

  // undo/redo can remove the sheet we're on
  const sheet = book.sheets[Math.min(sheetIx, book.sheets.length - 1)];
  const rows = Math.max(sheet.rows + PAD_ROWS, 60);
  const cols = Math.max(sheet.cols + PAD_COLS, 12);
  const selRef = ref(sheet.name, sel.r, sel.c);
  const range = {
    r0: Math.min(sel.r, ext.r),
    r1: Math.max(sel.r, ext.r),
    c0: Math.min(sel.c, ext.c),
    c1: Math.max(sel.c, ext.c),
  };
  const multi = range.r0 !== range.r1 || range.c0 !== range.c1;
  const fullRows = range.c0 === 0 && range.c1 === cols - 1; // whole rows selected
  const fullCols = range.r0 === 0 && range.r1 === rows - 1;
  const rangeLabel = multi ? `${colName(range.c0)}${range.r0 + 1}:${colName(range.c1)}${range.r1 + 1}` : selRef.slice(selRef.lastIndexOf("!") + 1);
  const inRange = (r: number, c: number) => r >= range.r0 && r <= range.r1 && c >= range.c0 && c <= range.c1;
  const eachInRange = (fn: (r: number, c: number) => void) => {
    for (let r = range.r0; r <= range.r1; r++) for (let c = range.c0; c <= range.c1; c++) fn(r, c);
  };
  const widths = Array.from({ length: cols }, (_, c) => sheet.colWidths[c] ?? DEFAULT_COL);
  const tableWidth = ROW_HEAD + widths.reduce((a, b) => a + b, 0);

  const peerAt = useMemo(() => new Map((peers ?? []).map((p) => [normalizeRef(p.cell), p])), [peers]);
  // "r:c" -> whose highlighted range covers the cell, on this sheet
  const peerRange = useMemo(() => {
    const at = new Map<string, { color: string; name: string }>();
    for (const p of peers ?? []) {
      if (!p.range) continue;
      const i = p.range.lastIndexOf("!");
      if (p.range.slice(0, i) !== sheet.name) continue;
      const { s: a, e: b } = XLSX.utils.decode_range(p.range.slice(i + 1));
      for (let r = a.r; r <= Math.min(b.r, a.r + 500); r++)
        for (let c = a.c; c <= Math.min(b.c, a.c + 100); c++) if (!at.has(`${r}:${c}`)) at.set(`${r}:${c}`, p);
    }
    return at;
  }, [peers, sheet.name]);

  const staleBySheet = useMemo(() => {
    const counts = new Map<string, number>();
    for (const c of constants.values()) {
      if (c.check?.status !== "stale") continue;
      const name = c.cell.slice(0, c.cell.lastIndexOf("!"));
      counts.set(name, (counts.get(name) ?? 0) + 1);
    }
    return counts;
  }, [constants]);

  useEffect(() => {
    // a right-click selects without scrolling, which would close the menu it opens
    if (keepScroll.current) return void (keepScroll.current = false);
    gridRef.current
      ?.querySelector(`[data-cell="${ext.r}:${ext.c}"]`)
      ?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [ext, sheetIx]);

  // While the mouse is held, track it anywhere on the page and scroll the grid when it leaves the edge.
  useEffect(() => {
    if (!drag) return;
    const grid = gridRef.current!;
    let pointer = pointerRef.current; // where the press happened
    const track = () => {
      const el = document.elementFromPoint(pointer.x, pointer.y)?.closest<HTMLElement>("[data-cell], [data-row], [data-col]");
      if (!el || !grid.contains(el)) return;
      const r = el.dataset.cell ? Number(el.dataset.cell.split(":")[0]) : el.dataset.row != null ? Number(el.dataset.row) : null;
      const c = el.dataset.cell ? Number(el.dataset.cell.split(":")[1]) : el.dataset.col != null ? Number(el.dataset.col) : null;
      setExt((e) => ({
        r: drag === "col" ? e.r : (r ?? e.r),
        c: drag === "row" ? e.c : (c ?? e.c),
      }));
    };
    const onMove = (e: MouseEvent) => {
      pointer = { x: e.clientX, y: e.clientY };
      track();
    };
    const timer = setInterval(() => {
      const b = grid.getBoundingClientRect();
      const dx = pointer.x < b.left + ROW_HEAD ? -1 : pointer.x > b.right - 12 ? 1 : 0;
      const dy = pointer.y < b.top + 22 ? -1 : pointer.y > b.bottom - 12 ? 1 : 0;
      if (!dx && !dy) return;
      grid.scrollBy(drag === "row" ? 0 : dx * 24, drag === "col" ? 0 : dy * 24);
      // pin the pointer inside the grid so the cell under the edge is picked up
      const x = clamp(pointer.x, b.left + ROW_HEAD + 2, b.right - 14);
      const y = clamp(pointer.y, b.top + 24, b.bottom - 14);
      const saved = pointer;
      pointer = { x, y };
      track();
      pointer = saved;
    }, 50);
    const stop = () => setDrag(null);
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", stop);
    return () => {
      clearInterval(timer);
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", stop);
    };
  }, [drag]);

  useEffect(() => {
    if (!focus) return;
    const { sheet: name, row, col } = parseRef(focus.ref);
    const ix = book.sheets.findIndex((s) => s.name === name);
    if (ix < 0) return;
    setEdit(null);
    setSheetIx(ix);
    select({ r: row, c: col });
    gridRef.current?.focus();
  }, [focus, book]);

  const focusGrid = () => gridRef.current?.focus();
  const select = (p: Pos, extend = false) => {
    if (!extend) setSel(p);
    setExt(p);
  };

  /** Write several cells as one undo step and one reported change. */
  const writeCells = (cells: { r: number; c: number; text: string }[]) => {
    const todo = cells.filter(({ r, c, text }) => raw(book, sheet, r, c) !== text);
    if (!todo.length) return;
    const before = todo.map(({ r, c }) => raw(book, sheet, r, c));
    book.hf.batch(() => todo.forEach(({ r, c, text }) => write(book, sheet, r, c, text)));
    grow(todo);
    setVersion((v) => v + 1);
    setClip(null);
    onEdit?.(todo.map(({ r, c }, i) => ({ ref: ref(sheet.name, r, c), before: before[i], after: raw(book, sheet, r, c) })));
  };
  const writeCell = (r: number, c: number, text: string) => writeCells([{ r, c, text }]);
  /** A paste can land outside the used range; widen it so the new cells count. */
  const grow = (cells: { r: number; c: number; text?: string }[]) => {
    for (const { r, c, text } of cells) {
      if (text === "") continue;
      sheet.rows = Math.max(sheet.rows, r + 1);
      sheet.cols = Math.max(sheet.cols, c + 1);
    }
  };

  const move = (dr: number, dc: number, extend = false) => {
    const from = extend ? ext : sel;
    select({ r: clamp(from.r + dr, 0, rows - 1), c: clamp(from.c + dc, 0, cols - 1) }, extend);
  };

  /** Cmd/Ctrl+arrow: jump to the edge of the current block of data, like Excel. */
  const jump = (dr: number, dc: number, extend: boolean) => {
    const from = extend ? ext : sel;
    const filled = (r: number, c: number) => raw(book, sheet, r, c) !== "";
    const inside = (r: number, c: number) => r >= 0 && r < rows && c >= 0 && c < cols;
    let { r, c } = from;
    const next = () => ({ r: r + dr, c: c + dc });
    if (filled(r, c) && inside(next().r, next().c) && filled(next().r, next().c)) {
      while (inside(next().r, next().c) && filled(next().r, next().c)) ({ r, c } = next());
    } else {
      ({ r, c } = next());
      while (inside(r, c) && !filled(r, c) && inside(next().r, next().c)) ({ r, c } = next());
    }
    select({ r: clamp(r, 0, rows - 1), c: clamp(c, 0, cols - 1) }, extend);
  };

  /** Mouse down on a cell or header. Shift extends from the active cell. */
  const press = (e: ReactMouseEvent, p: Pos, kind: Drag) => {
    if (e.button !== 0) return;
    e.preventDefault(); // no text selection while dragging
    pointerRef.current = { x: e.clientX, y: e.clientY };
    if (edit) commit();
    pick(p, kind, e.shiftKey);
    setDrag(kind);
    focusGrid();
  };
  const pick = (p: Pos, kind: Drag, extend = false) => {
    if (extend) {
      setExt(kind === "col" ? { r: rows - 1, c: p.c } : kind === "row" ? { r: p.r, c: cols - 1 } : p);
    } else if (kind === "col") {
      setSel({ r: 0, c: p.c });
      setExt({ r: rows - 1, c: p.c });
    } else if (kind === "row") {
      setSel({ r: p.r, c: 0 });
      setExt({ r: p.r, c: cols - 1 });
    } else select(p);
  };

  /** Right-click: keep the selection if the click is inside it, else select what was clicked, then open the menu. */
  const openContext = (e: ReactMouseEvent, p: Pos, kind: Drag) => {
    e.preventDefault();
    if (edit) commit();
    const inside =
      kind === "cell" ? inRange(p.r, p.c) : kind === "row" ? fullRows && p.r >= range.r0 && p.r <= range.r1 : fullCols && p.c >= range.c0 && p.c <= range.c1;
    if (!inside) {
      keepScroll.current = true;
      pick(p, kind);
    }
    setTip(null);
    setCtx({ x: e.clientX, y: e.clientY, kind });
    focusGrid();
  };

  /** Copy or cut: shown values go to the system clipboard; formulas stay here for pasting back in. */
  const copy = (cut: boolean) => {
    // whole rows/columns copy only the part with data
    const r1 = Math.max(range.r0, Math.min(range.r1, sheet.rows - 1));
    const c1 = Math.max(range.c0, Math.min(range.c1, sheet.cols - 1));
    const src = { ...range, r1, c1 };
    const shown: string[][] = [];
    for (let r = src.r0; r <= src.r1; r++) {
      const row: string[] = [];
      for (let c = src.c0; c <= src.c1; c++) row.push(view(book, sheet, r, c).text);
      shown.push(row);
    }
    const tsv = toTsv(shown);
    setClip({ sheetId: sheet.id, range: src, cut, tsv });
    return { tsv, html: toHtml(shown) };
  };

  /** Paste clipboard text. Values only drops formulas and formats from our own copies. */
  const paste = (text: string, valuesOnly = false) => {
    if (!text) return;
    const ours = clip && text.replace(/\r\n/g, "\n").replace(/\n$/, "") === clip.tsv ? clip : null;
    const from = ours && book.sheets.find((s) => s.id === ours.sheetId);
    if (ours && from && ours.cut && !valuesOnly) return pasteCut(ours, from);

    // the block to paste: formulas (or computed values) from our own copy, else the clipboard's text
    let block: string[][];
    if (ours && from) {
      block = [];
      for (let r = ours.range.r0; r <= ours.range.r1; r++) {
        const row: string[] = [];
        for (let c = ours.range.c0; c <= ours.range.c1; c++) row.push(valuesOnly ? value(from, r, c) : raw(book, from, r, c));
        block.push(row);
      }
    } else block = fromTsv(text);
    const formulas = ours && !valuesOnly;
    const h = block.length;
    const w = Math.max(...block.map((r) => r.length));

    // like Excel: a block that fits the selection a whole number of times fills it
    const selH = range.r1 - range.r0 + 1;
    const selW = range.c1 - range.c0 + 1;
    const tile = multi && selH % h === 0 && selW % w === 0;
    const outH = tile ? selH : h;
    const outW = tile ? selW : w;
    const top = range.r0;
    const left = range.c0;

    const cells: { r: number; c: number; text: string }[] = [];
    for (let i = 0; i < outH; i++)
      for (let j = 0; j < outW; j++) {
        const r = top + i;
        const c = left + j;
        let t = block[i % h][j % w] ?? "";
        if (formulas) t = shiftFormula(t, r - (ours.range.r0 + (i % h)), c - (ours.range.c0 + (j % w)));
        cells.push({ r, c, text: t });
        if (formulas && from) {
          const fmt = book.formats.get(ref(from.name, ours.range.r0 + (i % h), ours.range.c0 + (j % w)));
          if (fmt) book.formats.set(ref(sheet.name, r, c), fmt);
        }
      }
    const keep = clip; // a copy stays live for more pastes, as in Excel
    writeCells(cells);
    if (ours && !ours.cut) setClip(keep);
    setSel({ r: top, c: left });
    setExt({ r: top + outH - 1, c: left + outW - 1 });
  };

  /** A cell's computed value as text a paste can write back: numbers unformatted, errors as shown. */
  const value = (s: typeof sheet, r: number, c: number) => {
    const v = book.hf.getCellValue({ sheet: s.id, row: r, col: c });
    return v === null || v === undefined ? "" : typeof v === "object" ? view(book, s, r, c).text : String(v);
  };

  /** Cut + paste moves the cells; formulas that pointed at them follow. */
  const pasteCut = (cut: Clip, from: typeof sheet) => {
    const h = cut.range.r1 - cut.range.r0 + 1;
    const w = cut.range.c1 - cut.range.c0 + 1;
    const dest = { r: range.r0, c: range.c0 };
    const touched = new Map<string, { s: typeof sheet; r: number; c: number }>();
    for (let i = 0; i < h; i++)
      for (let j = 0; j < w; j++) {
        touched.set(ref(from.name, cut.range.r0 + i, cut.range.c0 + j), { s: from, r: cut.range.r0 + i, c: cut.range.c0 + j });
        touched.set(ref(sheet.name, dest.r + i, dest.c + j), { s: sheet, r: dest.r + i, c: dest.c + j });
      }
    const before = new Map([...touched].map(([k, t]) => [k, raw(book, t.s, t.r, t.c)]));
    const formats = [...touched.keys()].map((k) => book.formats.get(k));
    book.hf.cut({ start: { sheet: from.id, row: cut.range.r0, col: cut.range.c0 }, end: { sheet: from.id, row: cut.range.r1, col: cut.range.c1 } });
    book.hf.paste({ sheet: sheet.id, row: dest.r, col: dest.c });
    // formats travel with the cells
    const keys = [...touched.keys()];
    for (let i = 0; i < h; i++)
      for (let j = 0; j < w; j++) {
        const src = ref(from.name, cut.range.r0 + i, cut.range.c0 + j);
        const fmt = formats[keys.indexOf(src)];
        book.formats.delete(src);
        if (fmt) book.formats.set(ref(sheet.name, dest.r + i, dest.c + j), fmt);
      }
    grow([dest, { r: dest.r + h - 1, c: dest.c + w - 1 }]);
    setVersion((v) => v + 1);
    setClip(null);
    setSel(dest);
    setExt({ r: dest.r + h - 1, c: dest.c + w - 1 });
    const changes = [...touched]
      .map(([k, t]) => ({ ref: k, before: before.get(k)!, after: raw(book, t.s, t.r, t.c) }))
      .filter((ch) => ch.before !== ch.after);
    onEdit?.(changes, h * w); // even with nothing changed, the paste is a step to undo
  };

  // copy/cut/paste events land on the document, since the grid isn't an editable element
  const clipboardRef = useRef({ copy, paste, edit });
  clipboardRef.current = { copy, paste, edit };
  useEffect(() => {
    const ours = () => document.activeElement === gridRef.current && !clipboardRef.current.edit;
    const put = (e: ClipboardEvent, cut: boolean) => {
      const { tsv, html } = clipboardRef.current.copy(cut);
      e.clipboardData?.setData("text/plain", tsv);
      e.clipboardData?.setData("text/html", html);
      e.preventDefault();
    };
    const onCopy = (e: ClipboardEvent) => ours() && put(e, false);
    const onCut = (e: ClipboardEvent) => ours() && put(e, true);
    const onPaste = (e: ClipboardEvent) => {
      if (!ours()) return;
      e.preventDefault();
      clipboardRef.current.paste(e.clipboardData?.getData("text/plain") ?? "", valuesOnly.current);
      valuesOnly.current = false;
    };
    document.addEventListener("copy", onCopy);
    document.addEventListener("cut", onCut);
    document.addEventListener("paste", onPaste);
    return () => {
      document.removeEventListener("copy", onCopy);
      document.removeEventListener("cut", onCut);
      document.removeEventListener("paste", onPaste);
    };
  }, []);

  // Enter or Tab commits, then the editor's blur fires with the same edit: write it once
  const committed = useRef<Edit | null>(null);
  const commit = (dr = 0, dc = 0) => {
    if (edit && committed.current !== edit) writeCell(sel.r, sel.c, edit.text);
    committed.current = edit;
    setEdit(null);
    // Enter/Tab commit, then the editor's blur commits again with the old selection: only
    // an actual move may select, or the blur would snap the cursor back
    if (dr || dc) move(dr, dc);
    focusGrid();
  };

  const cancel = () => {
    setEdit(null);
    focusGrid();
  };

  const history = (redo: boolean) => {
    if (redo ? book.hf.isThereSomethingToRedo() : book.hf.isThereSomethingToUndo()) {
      redo ? book.hf.redo() : book.hf.undo();
      syncSheets(book);
      setVersion((v) => v + 1);
      onHistory?.(redo);
    }
  };

  const onGridKey = (e: KeyboardEvent) => {
    if (edit) return; // the input handles its own keys
    const mod = e.metaKey || e.ctrlKey;
    if (mod && e.key.toLowerCase() === "z") return e.preventDefault(), history(e.shiftKey);
    if (mod && e.key.toLowerCase() === "y") return e.preventDefault(), history(true);
    // the paste event that follows can't tell if shift was held
    if (mod && e.key.toLowerCase() === "v") valuesOnly.current = e.shiftKey;
    if (mod && e.key.toLowerCase() === "a") {
      e.preventDefault();
      setSel({ r: 0, c: 0 });
      return setExt({ r: rows - 1, c: cols - 1 });
    }

    const arrows: Record<string, [number, number]> = {
      ArrowUp: [-1, 0],
      ArrowDown: [1, 0],
      ArrowLeft: [0, -1],
      ArrowRight: [0, 1],
    };
    if (arrows[e.key]) {
      e.preventDefault();
      return mod ? jump(...arrows[e.key], e.shiftKey) : move(...arrows[e.key], e.shiftKey);
    }
    if (mod) return;
    if (e.key === "Escape") return setExt(sel), setClip(null);
    if (e.key === "Tab") return e.preventDefault(), move(0, e.shiftKey ? -1 : 1);
    if (e.key === "Enter" || e.key === "F2") {
      e.preventDefault();
      return setEdit({ text: raw(book, sheet, sel.r, sel.c), from: "cell" });
    }
    if (e.key === "Backspace" || e.key === "Delete") return e.preventDefault(), clearRange();
    if (e.key.length === 1 && !e.altKey) {
      e.preventDefault();
      setEdit({ text: e.key, from: "cell" });
    }
  };

  const clearRange = () => {
    // whole rows/columns only need the used part cleared
    const cells: { r: number; c: number; text: string }[] = [];
    eachInRange((r, c) => r < sheet.rows && c < sheet.cols && cells.push({ r, c, text: "" }));
    writeCells(cells);
  };

  /** Menu copy/cut write to the system clipboard directly, since there's no copy event to fill. */
  const menuCopy = async (cut: boolean) => {
    const { tsv, html } = copy(cut);
    try {
      await navigator.clipboard.write([
        new ClipboardItem({ "text/plain": new Blob([tsv], { type: "text/plain" }), "text/html": new Blob([html], { type: "text/html" }) }),
      ]);
    } catch {
      await navigator.clipboard.writeText(tsv).catch(() => {});
    }
  };
  const menuPaste = async (valuesOnly: boolean) => {
    try {
      paste(await navigator.clipboard.readText(), valuesOnly);
    } catch {
      alert(`Your browser blocked pasting from the menu. Use ${MOD}V${valuesOnly ? ` (${MOD}${SHIFT}V for values only)` : ""} instead.`);
    }
    focusGrid();
  };

  /** Insert or delete the selected rows/columns, as one timeline entry. */
  const lines = (axis: "row" | "col", at: number, count: number) => {
    if (!shiftLines(book, sheet, axis, at, count)) return;
    setClip(null);
    setVersion((v) => v + 1);
    const n = Math.abs(count);
    const what = axis === "row" ? `${n} ${n === 1 ? "row" : "rows"}` : `${n} ${n === 1 ? "column" : "columns"}`;
    const where = axis === "row" ? `${at + 1}` : colName(at);
    onEdit?.([{ ref: ref(sheet.name, axis === "row" ? at : 0, axis === "col" ? at : 0), before: "", after: "" }], undefined, `${what} ${count > 0 ? "inserted at" : "deleted from"} ${axis === "row" ? "row" : "column"} ${where}`);
    if (count < 0) {
      // the selection collapses onto what moved into the deleted space
      const p = { r: axis === "row" ? range.r0 : sel.r, c: axis === "col" ? range.c0 : sel.c };
      setSel(p);
      setExt(axis === "row" && fullRows ? { r: p.r, c: cols - 1 } : axis === "col" && fullCols ? { r: rows - 1, c: p.c } : p);
    } else if (axis === "row" && at > range.r0) {
      // inserting below keeps the selection where it is
    } else if (axis === "row") {
      setSel((s) => ({ ...s, r: s.r + count }));
      setExt((s) => ({ ...s, r: s.r + count }));
    } else if (at <= range.c0) {
      setSel((s) => ({ ...s, c: s.c + count }));
      setExt((s) => ({ ...s, c: s.c + count }));
    }
    focusGrid();
  };

  const ctxItems = (kind: Drag): MenuItem[] => {
    const nr = range.r1 - range.r0 + 1;
    const nc = range.c1 - range.c0 + 1;
    const rowsLabel = nr === 1 ? "1 row" : `${nr} rows`;
    const colsLabel = nc === 1 ? "1 column" : `${nc} columns`;
    // a whole column selected has no meaningful row count, and vice versa
    const rowOps = !fullCols;
    const colOps = !fullRows;
    const items: MenuItem[] = [
      { label: "Cut", hint: `${MOD}X`, onSelect: () => menuCopy(true) },
      { label: "Copy", hint: `${MOD}C`, onSelect: () => menuCopy(false) },
      { label: "Paste", hint: `${MOD}V`, onSelect: () => menuPaste(false) },
      { label: "Paste values only", hint: `${MOD}${SHIFT}V`, onSelect: () => menuPaste(true) },
      "divider",
    ];
    if (kind !== "col" && rowOps) {
      items.push({ label: `Insert ${rowsLabel} above`, onSelect: () => lines("row", range.r0, nr) });
      if (kind === "row") items.push({ label: `Insert ${rowsLabel} below`, onSelect: () => lines("row", range.r1 + 1, nr) });
    }
    if (kind !== "row" && colOps) {
      items.push({ label: `Insert ${colsLabel} left`, onSelect: () => lines("col", range.c0, nc) });
      if (kind === "col") items.push({ label: `Insert ${colsLabel} right`, onSelect: () => lines("col", range.c1 + 1, nc) });
    }
    items.push("divider");
    const span = (a: number, b: number, name: (n: number) => string) => (a === b ? name(a) : `${name(a)}–${name(b)}`);
    if (kind !== "col" && rowOps)
      items.push({ label: `Delete ${nr === 1 ? "row" : `rows ${span(range.r0, range.r1, (n) => `${n + 1}`)}`}`, onSelect: () => lines("row", range.r0, -nr) });
    if (kind !== "row" && colOps)
      items.push({ label: `Delete ${nc === 1 ? "column" : `columns ${span(range.c0, range.c1, colName)}`}`, onSelect: () => lines("col", range.c0, -nc) });
    if (kind !== "cell")
      items.push({ label: kind === "row" ? (nr === 1 ? "Clear row" : `Clear rows ${span(range.r0, range.r1, (n) => `${n + 1}`)}`) : nc === 1 ? "Clear column" : `Clear columns ${span(range.c0, range.c1, colName)}`, onSelect: clearRange });
    else items.push({ label: "Clear contents", hint: "Delete", onSelect: clearRange });
    // the menu took focus; hand it back so the keyboard keeps working on the grid
    return items.map((i) => (i === "divider" ? i : { ...i, onSelect: () => (i.onSelect(), focusGrid()) }));
  };

  const onEditKey = (e: KeyboardEvent) => {
    if (e.key === "Enter") return e.preventDefault(), commit(e.shiftKey ? -1 : 1, 0);
    if (e.key === "Tab") return e.preventDefault(), commit(0, e.shiftKey ? -1 : 1);
    if (e.key === "Escape") return e.preventDefault(), cancel();
  };

  const switchSheet = (ix: number) => {
    setEdit(null);
    setSheetIx(ix);
    select({ r: 0, c: 0 });
    focusGrid();
  };

  const newSheet = () => {
    switchSheet(addSheet(book));
    onEdit?.([]);
  };
  const commitRename = () => {
    if (renaming && renameSheet(book, renaming.ix, renaming.text)) onEdit?.([]);
    setRenaming(null);
    setVersion((v) => v + 1);
  };
  const deleteSheet = (ix: number) => {
    if (!canDeleteSheets) return;
    const name = book.sheets[ix].name;
    if (!confirm(`Delete "${name}"? Formulas that point at it will show #REF!.`)) return;
    const count = book.sheets.length;
    removeSheet(book, ix);
    if (book.sheets.length < count) onEdit?.([]);
    switchSheet(Math.max(0, Math.min(ix, book.sheets.length - 1)));
    setVersion((v) => v + 1);
  };

  // version is read so the grid re-renders after edits recalc the workbook
  void version;
  const barText = edit ? edit.text : raw(book, sheet, sel.r, sel.c);
  const fmt = getFormat(book, sheet, sel.r, sel.c);
  const fmtLabel = FORMATS.find((f) => f.fmt === fmt)?.label ?? "Custom";
  const applyFormat = (next: string) => {
    eachInRange((r, c) => setFormat(book, sheet, r, c, next));
    setVersion((v) => v + 1);
    focusGrid();
  };
  const rangeRef = multi ? `${sheet.name}!${rangeLabel}` : undefined;
  useEffect(() => onSelectCell?.(selRef, rangeRef), [selRef, rangeRef]);

  // hovering a checked constant shows its card beside the cell
  const [tip, setTip] = useState<{ ref: string; left: number; top: number; bottom: number } | null>(null);
  const hover = (e: ReactMouseEvent) => {
    const td = (e.target as HTMLElement).closest<HTMLElement>("td[data-cell]");
    const [r, c] = td?.dataset.cell?.split(":").map(Number) ?? [];
    const key = td ? ref(sheet.name, r, c) : null;
    if (!td || drag || !key || !constants.has(key)) return setTip(null);
    if (tip?.ref === key) return;
    const b = td.getBoundingClientRect();
    setTip({ ref: key, left: b.left, top: b.top, bottom: b.bottom });
  };
  const tipConstant = tip && !(edit?.from === "cell" && tip.ref === selRef) ? constants.get(tip.ref) : undefined;

  return (
    <div className="sheet" ref={rootRef}>
      <div className="toolbar" role="toolbar" aria-label="Sheet tools">
        <div className="tb-group">
          <button className="tb-btn" onClick={() => history(false)} aria-label="Undo" title="Undo">
            <Undo />
          </button>
          <button className="tb-btn" onClick={() => history(true)} aria-label="Redo" title="Redo">
            <Redo />
          </button>
        </div>
        <div className="tb-group">
          <Menu
            label="Number format"
            className="tb-format"
            trigger={
              <>
                <span>{fmtLabel}</span>
                <Chevron />
              </>
            }
            items={FORMATS.map((f) => ({ label: f.label, hint: f.example, onSelect: () => applyFormat(f.fmt) }))}
          />
        </div>
        <div className="tb-group">
          <button className="tb-btn" onClick={() => applyFormat(shiftDecimals(fmt, -1))} aria-label="Fewer decimal places" title="Fewer decimals">
            <DecLess />
          </button>
          <button className="tb-btn" onClick={() => applyFormat(shiftDecimals(fmt, 1))} aria-label="More decimal places" title="More decimals">
            <DecMore />
          </button>
        </div>
        <div className="tb-spacer" />
        {toolbarEnd}
      </div>
      <div className="formula-bar">
        <span className="name-box mono">{rangeLabel}</span>
        <input
          className="formula-input mono"
          value={barText}
          spellCheck={false}
          aria-label={`Contents of ${selRef}`}
          onFocus={() => !edit && setEdit({ text: barText, from: "bar" })}
          onChange={(e) => setEdit({ text: e.target.value, from: "bar" })}
          onKeyDown={onEditKey}
          onBlur={() => edit?.from === "bar" && commit()}
        />
      </div>
      {tip && tipConstant && (
        <ConstantStrip
          constant={tipConstant}
          style={{
            left: Math.min(tip.left, window.innerWidth - 300),
            ...(tip.bottom + 140 > window.innerHeight ? { bottom: window.innerHeight - tip.top + 6 } : { top: tip.bottom + 6 }),
          }}
        />
      )}

      <div
        className={`grid${drag ? " dragging" : ""}`}
        ref={gridRef}
        tabIndex={0}
        onKeyDown={onGridKey}
        onMouseOver={hover}
        onMouseLeave={() => setTip(null)}
        onScroll={() => setTip(null)}
        aria-label={`${sheet.name} grid`}
      >
        <table style={{ width: tableWidth }}>
          <colgroup>
            <col style={{ width: ROW_HEAD }} />
            {widths.map((w, c) => (
              <col key={c} style={{ width: w }} />
            ))}
          </colgroup>
          <thead>
            <tr>
              <th
                className="corner"
                onMouseDown={(e) => {
                  e.preventDefault();
                  setSel({ r: 0, c: 0 });
                  setExt({ r: rows - 1, c: cols - 1 });
                  focusGrid();
                }}
              />
              {Array.from({ length: cols }, (_, c) => (
                <th
                  key={c}
                  data-col={c}
                  className={c >= range.c0 && c <= range.c1 ? (range.r0 === 0 && range.r1 === rows - 1 ? "on full" : "on") : undefined}
                  onMouseDown={(e) => press(e, { r: 0, c }, "col")}
                  onContextMenu={(e) => openContext(e, { r: 0, c }, "col")}
                >
                  {colName(c)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: rows }, (_, r) => (
              <tr key={r}>
                <th
                  data-row={r}
                  className={r >= range.r0 && r <= range.r1 ? (range.c0 === 0 && range.c1 === cols - 1 ? "on full" : "on") : undefined}
                  onMouseDown={(e) => press(e, { r, c: 0 }, "row")}
                  onContextMenu={(e) => openContext(e, { r, c: 0 }, "row")}
                >
                  {r + 1}
                </th>
                {Array.from({ length: cols }, (_, c) => {
                  const isSel = r === sel.r && c === sel.c;
                  const peer = peerAt.get(ref(sheet.name, r, c));
                  const peerIn = peerRange.get(`${r}:${c}`);
                  const hit = multi && inRange(r, c);
                  const v = view(book, sheet, r, c);
                  const constant = constants.get(ref(sheet.name, r, c));
                  const cls = [
                    v.kind,
                    v.input && "input",
                    constant?.check?.status === "stale" && "stale",
                    isSel && "selected",
                    clip?.sheetId === sheet.id && clipEdges(clip.range, r, c),
                    hit && !isSel && "in-range",
                    hit && r === range.r0 && "rt",
                    hit && r === range.r1 && "rb",
                    hit && c === range.c0 && "rl",
                    hit && c === range.c1 && "rr",
                    peer && "peer",
                    peerIn && !hit && !isSel && "peer-range",
                  ]
                    .filter(Boolean)
                    .join(" ");
                  return (
                    <td
                      key={c}
                      data-cell={`${r}:${c}`}
                      className={cls}
                      title={peer ? peer.name : v.text.length > 14 ? v.text : undefined}
                      style={peer || peerIn ? ({ "--peer": (peer ?? peerIn)!.color } as CSSProperties) : undefined}
                      data-peer={peer?.name.split(" ")[0]}
                      onMouseDown={(e) => {
                        if (isSel && edit?.from === "cell") return; // clicks inside the editor
                        press(e, { r, c }, "cell");
                      }}
                      onDoubleClick={() => setEdit({ text: raw(book, sheet, r, c), from: "cell" })}
                      onContextMenu={(e) => {
                        if (isSel && edit?.from === "cell") return; // the editor keeps the browser's menu
                        openContext(e, { r, c }, "cell");
                      }}
                    >
                      {isSel && edit?.from === "cell" ? (
                        <input
                          className="cell-input mono"
                          autoFocus
                          value={edit.text}
                          spellCheck={false}
                          onChange={(e) => setEdit({ text: e.target.value, from: "cell" })}
                          onKeyDown={onEditKey}
                          onBlur={() => commit()}
                        />
                      ) : (
                        v.text
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <nav className="tabs" aria-label="Sheets">
        {book.sheets.map((s, ix) => {
          const stale = staleBySheet.get(s.name);
          const on = s === sheet;
          if (renaming?.ix === ix)
            return (
              <input
                key={s.id}
                className="tab-rename"
                value={renaming.text}
                autoFocus
                size={Math.max(renaming.text.length, 4)}
                aria-label="Sheet name"
                onFocus={(e) => e.target.select()}
                onChange={(e) => setRenaming({ ix, text: e.target.value })}
                onKeyDown={(e) => {
                  if (e.key === "Enter") commitRename();
                  if (e.key === "Escape") setRenaming(null);
                }}
                onBlur={commitRename}
              />
            );
          return (
            <div key={s.id} className={`tab ${on ? "on" : ""}`}>
              <button
                onClick={() => switchSheet(ix)}
                onDoubleClick={() => setRenaming({ ix, text: s.name })}
                onContextMenu={(e) => {
                  e.preventDefault();
                  if (!on) switchSheet(ix);
                  const tab = e.currentTarget.parentElement!.getBoundingClientRect();
                  setTabMenu({ ix, left: tab.left - rootRef.current!.getBoundingClientRect().left });
                }}
                title="Double-click or right-click to rename"
              >
                {s.name}
                {stale ? <span className="tab-stale mono">{stale}</span> : null}
              </button>
              {on && (
                <button
                  className="tab-more"
                  aria-label={`${s.name} options`}
                  aria-haspopup="menu"
                  aria-expanded={tabMenu?.ix === ix}
                  onClick={(e) => {
                    const tab = e.currentTarget.parentElement!.getBoundingClientRect();
                    const root = rootRef.current!.getBoundingClientRect();
                    setTabMenu(tabMenu ? null : { ix, left: tab.left - root.left });
                  }}
                >
                  <Chevron />
                </button>
              )}
            </div>
          );
        })}
        <button className="tab-add" onClick={newSheet} aria-label="Add sheet" title="Add sheet">
          +
        </button>
      </nav>
      {ctx && <ContextMenu x={ctx.x} y={ctx.y} items={ctxItems(ctx.kind)} onClose={closeCtx} />}
      {tabMenu && (
        <div className="menu-pop tab-pop" role="menu" style={{ left: tabMenu.left }}>
          <button
            role="menuitem"
            onClick={() => {
              setRenaming({ ix: tabMenu.ix, text: book.sheets[tabMenu.ix].name });
              setTabMenu(null);
            }}
          >
            Rename
          </button>
          <button
            role="menuitem"
            disabled={book.sheets.length < 2 || !canDeleteSheets}
            title={canDeleteSheets ? undefined : "Only the owner can delete sheets"}
            onClick={() => {
              setTabMenu(null);
              deleteSheet(tabMenu.ix);
            }}
          >
            Delete
          </button>
        </div>
      )}
    </div>
  );
}

const clamp = (n: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, n));

/** Classes for the dashed "copied" outline on the edge cells of the clipboard range. */
function clipEdges(r: Range, row: number, col: number) {
  if (row < r.r0 || row > r.r1 || col < r.c0 || col > r.c1) return false;
  return [
    "clip",
    row === r.r0 && "ct",
    row === r.r1 && "cb",
    col === r.c0 && "cl",
    col === r.c1 && "cr",
  ]
    .filter(Boolean)
    .join(" ");
}

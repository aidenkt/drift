import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import type { Constant } from "../types";
import { colName, FORMATS, getFormat, parseRef, raw, ref, setFormat, shiftDecimals, view, write, type Book } from "../lib/workbook";
import { Chevron, DecLess, DecMore, Redo, Undo } from "./icons";
import Menu from "./Menu";
import ConstantStrip from "./ConstantStrip";

const DEFAULT_COL = 96;
const ROW_HEAD = 44;
const PAD_ROWS = 30;
const PAD_COLS = 4;

type Edit = { text: string; from: "cell" | "bar" };

type Props = {
  book: Book;
  constants: Map<string, Constant>;
  /** Jump to a cell; nonce lets the same ref be focused twice. */
  focus?: { ref: string; nonce: number } | null;
  onEdit?: (ref: string, before: string, after: string) => void;
  /** Bumped by the page after undo/redo from the menu bar, to re-render. */
  rev?: number;
  toolbarEnd?: ReactNode;
};

export default function Spreadsheet({ book, constants, focus, onEdit, toolbarEnd }: Props) {
  const [sheetIx, setSheetIx] = useState(0);
  const [sel, setSel] = useState({ r: 0, c: 0 });
  const [edit, setEdit] = useState<Edit | null>(null);
  const [version, setVersion] = useState(0);
  const gridRef = useRef<HTMLDivElement>(null);

  const sheet = book.sheets[sheetIx];
  const rows = Math.max(sheet.rows + PAD_ROWS, 60);
  const cols = Math.max(sheet.cols + PAD_COLS, 12);
  const selRef = ref(sheet.name, sel.r, sel.c);
  const widths = Array.from({ length: cols }, (_, c) => sheet.colWidths[c] ?? DEFAULT_COL);
  const tableWidth = ROW_HEAD + widths.reduce((a, b) => a + b, 0);

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
    gridRef.current
      ?.querySelector(`[data-cell="${sel.r}:${sel.c}"]`)
      ?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [sel, sheetIx]);

  useEffect(() => {
    if (!focus) return;
    const { sheet: name, row, col } = parseRef(focus.ref);
    const ix = book.sheets.findIndex((s) => s.name === name);
    if (ix < 0) return;
    setEdit(null);
    setSheetIx(ix);
    setSel({ r: row, c: col });
    gridRef.current?.focus();
  }, [focus, book]);

  const focusGrid = () => gridRef.current?.focus();

  const writeCell = (r: number, c: number, text: string) => {
    const before = raw(book, sheet, r, c);
    if (before === text) return;
    write(book, sheet, r, c, text);
    setVersion((v) => v + 1);
    onEdit?.(ref(sheet.name, r, c), before, raw(book, sheet, r, c));
  };

  const move = (dr: number, dc: number) =>
    setSel((s) => ({ r: clamp(s.r + dr, 0, rows - 1), c: clamp(s.c + dc, 0, cols - 1) }));

  const commit = (dr = 0, dc = 0) => {
    if (edit) writeCell(sel.r, sel.c, edit.text);
    setEdit(null);
    move(dr, dc);
    focusGrid();
  };

  const cancel = () => {
    setEdit(null);
    focusGrid();
  };

  const history = (redo: boolean) => {
    if (redo ? book.hf.isThereSomethingToRedo() : book.hf.isThereSomethingToUndo()) {
      redo ? book.hf.redo() : book.hf.undo();
      setVersion((v) => v + 1);
    }
  };

  const onGridKey = (e: KeyboardEvent) => {
    if (edit) return; // the input handles its own keys
    const mod = e.metaKey || e.ctrlKey;
    if (mod && e.key.toLowerCase() === "z") return e.preventDefault(), history(e.shiftKey);
    if (mod && e.key.toLowerCase() === "y") return e.preventDefault(), history(true);
    if (mod) return;

    const arrows: Record<string, [number, number]> = {
      ArrowUp: [-1, 0],
      ArrowDown: [1, 0],
      ArrowLeft: [0, -1],
      ArrowRight: [0, 1],
    };
    if (arrows[e.key]) return e.preventDefault(), move(...arrows[e.key]);
    if (e.key === "Tab") return e.preventDefault(), move(0, e.shiftKey ? -1 : 1);
    if (e.key === "Enter" || e.key === "F2") {
      e.preventDefault();
      return setEdit({ text: raw(book, sheet, sel.r, sel.c), from: "cell" });
    }
    if (e.key === "Backspace" || e.key === "Delete") {
      e.preventDefault();
      return writeCell(sel.r, sel.c, "");
    }
    if (e.key.length === 1 && !e.altKey) {
      e.preventDefault();
      setEdit({ text: e.key, from: "cell" });
    }
  };

  const onEditKey = (e: KeyboardEvent) => {
    if (e.key === "Enter") return e.preventDefault(), commit(e.shiftKey ? -1 : 1, 0);
    if (e.key === "Tab") return e.preventDefault(), commit(0, e.shiftKey ? -1 : 1);
    if (e.key === "Escape") return e.preventDefault(), cancel();
  };

  const switchSheet = (ix: number) => {
    setEdit(null);
    setSheetIx(ix);
    setSel({ r: 0, c: 0 });
    focusGrid();
  };

  // version is read so the grid re-renders after edits recalc the workbook
  void version;
  const barText = edit ? edit.text : raw(book, sheet, sel.r, sel.c);
  const fmt = getFormat(book, sheet, sel.r, sel.c);
  const fmtLabel = FORMATS.find((f) => f.fmt === fmt)?.label ?? "Custom";
  const applyFormat = (next: string) => {
    setFormat(book, sheet, sel.r, sel.c, next);
    setVersion((v) => v + 1);
    focusGrid();
  };
  const selected = constants.get(selRef);

  return (
    <div className="sheet">
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
        <span className="name-box mono">{selRef}</span>
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
      {selected && <ConstantStrip constant={selected} />}

      <div className="grid" ref={gridRef} tabIndex={0} onKeyDown={onGridKey} aria-label={`${sheet.name} grid`}>
        <table style={{ width: tableWidth }}>
          <colgroup>
            <col style={{ width: ROW_HEAD }} />
            {widths.map((w, c) => (
              <col key={c} style={{ width: w }} />
            ))}
          </colgroup>
          <thead>
            <tr>
              <th className="corner" />
              {Array.from({ length: cols }, (_, c) => (
                <th key={c} className={c === sel.c ? "on" : undefined}>
                  {colName(c)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: rows }, (_, r) => (
              <tr key={r}>
                <th className={r === sel.r ? "on" : undefined}>{r + 1}</th>
                {Array.from({ length: cols }, (_, c) => {
                  const isSel = r === sel.r && c === sel.c;
                  const v = view(book, sheet, r, c);
                  const constant = constants.get(ref(sheet.name, r, c));
                  const cls = [
                    v.kind,
                    v.input && "input",
                    constant?.check?.status === "stale" && "stale",
                    isSel && "selected",
                  ]
                    .filter(Boolean)
                    .join(" ");
                  return (
                    <td
                      key={c}
                      data-cell={`${r}:${c}`}
                      className={cls}
                      title={v.text.length > 14 ? v.text : undefined}
                      onMouseDown={() => {
                        if (edit) commit();
                        setSel({ r, c });
                      }}
                      onDoubleClick={() => setEdit({ text: raw(book, sheet, r, c), from: "cell" })}
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
          return (
            <button key={s.id} className={ix === sheetIx ? "on" : undefined} onClick={() => switchSheet(ix)}>
              {s.name}
              {stale ? <span className="tab-stale mono">{stale}</span> : null}
            </button>
          );
        })}
      </nav>
    </div>
  );
}

const clamp = (n: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, n));

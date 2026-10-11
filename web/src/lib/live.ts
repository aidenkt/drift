/** Live edits between people with the same workbook open. Each tab compares the workbook with
 *  how it last looked and sends what's different: cell contents, sheets and number formats.
 *  Contents travel as values, not operations, so the last write to a cell wins everywhere,
 *  and undo, paste and inserted rows need nothing special. */
import * as XLSX from "xlsx";
import type { RawCellContent } from "hyperformula";
import { syncSheets, type Book } from "./workbook";

/** sheet name -> "A1" -> contents as JSON, empty cells left out; plus formats by "Sheet!A1" */
export type Snapshot = { sheets: Map<string, Map<string, string>>; formats: Map<string, string> };

export type CellsOp = {
  cells: Record<string, Record<string, RawCellContent>>; // sheet -> "A1" -> contents (null clears)
  added: string[]; // sheets
  removed: string[];
  formats: Record<string, string | null>;
};

export function snapshot(book: Book): Snapshot {
  const sheets = new Map<string, Map<string, string>>();
  for (const [name, rows] of Object.entries(book.hf.getAllSheetsSerialized())) {
    const cells = new Map<string, string>();
    rows.forEach((row, r) =>
      row.forEach((v, c) => {
        if (v !== null && v !== undefined && v !== "") cells.set(XLSX.utils.encode_cell({ r, c }), JSON.stringify(v));
      }),
    );
    sheets.set(name, cells);
  }
  return { sheets, formats: new Map(book.formats) };
}

/** What changed from `a` to `b`, or null when nothing did. */
export function diff(a: Snapshot, b: Snapshot): CellsOp | null {
  const op: CellsOp = { cells: {}, added: [], removed: [], formats: {} };
  let any = false;
  for (const [name, now] of b.sheets) {
    const before = a.sheets.get(name);
    if (!before) op.added.push(name), (any = true);
    const out: Record<string, RawCellContent> = {};
    for (const [addr, v] of now) if (before?.get(addr) !== v) out[addr] = JSON.parse(v);
    for (const addr of before?.keys() ?? []) if (!now.has(addr)) out[addr] = null;
    if (Object.keys(out).length) (op.cells[name] = out), (any = true);
  }
  for (const name of a.sheets.keys()) if (!b.sheets.has(name)) op.removed.push(name), (any = true);
  for (const [key, fmt] of b.formats) if (a.formats.get(key) !== fmt) (op.formats[key] = fmt), (any = true);
  for (const key of a.formats.keys()) if (!b.formats.has(key)) (op.formats[key] = null), (any = true);
  return any ? op : null;
}

/** Applies someone else's changes. Clears undo here, so undo can't take back their work. */
export function apply(book: Book, op: CellsOp) {
  const hf = book.hf;
  // a renamed sheet arrives as one added and one removed: rename it, so its tab keeps its place
  let { added, removed } = op;
  if (added.length === 1 && removed.length === 1) {
    const id = hf.getSheetId(removed[0]);
    if (id !== undefined && hf.isItPossibleToRenameSheet(id, added[0])) {
      hf.renameSheet(id, added[0]);
      [added, removed] = [[], []];
    }
  }
  // otherwise new sheets first and removed ones last, once formulas no longer point at them
  for (const name of added) if (hf.isItPossibleToAddSheet(name)) hf.addSheet(name);
  hf.batch(() => {
    for (const [name, cells] of Object.entries(op.cells)) {
      const id = hf.getSheetId(name);
      if (id === undefined) continue;
      for (const [addr, v] of Object.entries(cells)) {
        const { r, c } = XLSX.utils.decode_cell(addr);
        hf.setCellContents({ sheet: id, row: r, col: c }, [[v]]);
      }
    }
  });
  for (const name of removed) {
    const id = hf.getSheetId(name);
    if (id !== undefined && hf.getSheetNames().length > 1) hf.removeSheet(id);
  }
  for (const [key, fmt] of Object.entries(op.formats)) fmt === null ? book.formats.delete(key) : book.formats.set(key, fmt);
  syncSheets(book);
  // the grid draws each sheet's used range; it may have grown or shrunk
  for (const s of book.sheets) {
    const { height, width } = hf.getSheetDimensions(s.id);
    s.rows = height;
    s.cols = width;
  }
  hf.clearUndoStack();
  hf.clearRedoStack();
}

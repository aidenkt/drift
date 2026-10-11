import * as XLSX from "xlsx";
import { DetailedCellError, HyperFormula, type RawCellContent, type SimpleCellAddress } from "hyperformula";

export type SheetMeta = {
  id: number;
  name: string;
  rows: number; // used range, from A1
  cols: number;
  colWidths: (number | undefined)[]; // px
};

export type Book = {
  hf: HyperFormula;
  sheets: SheetMeta[];
  formats: Map<string, string>; // "Sheet!A1" -> Excel number format
  modified: string | null; // ISO time the file was last saved, from its document properties
};

export type CellView = {
  text: string;
  kind: "empty" | "number" | "text" | "bool" | "error";
  formula: boolean;
  input: boolean; // hardcoded number: blue, per banker convention
};

export const ref = (sheet: string, row: number, col: number) =>
  `${sheet}!${XLSX.utils.encode_cell({ r: row, c: col })}`;

export const colName = (col: number) => XLSX.utils.encode_col(col);

/** "P&L!C12" -> { sheet: "P&L", row: 11, col: 2 } */
export const parseRef = (r: string) => {
  const n = normalizeRef(r);
  const i = n.lastIndexOf("!");
  const { r: row, c: col } = XLSX.utils.decode_cell(n.slice(i + 1));
  return { sheet: n.slice(0, i), row, col };
};

/** "'P&L'!$C$12" -> "P&L!C12" so engine refs and grid refs compare equal. */
export const normalizeRef = (r: string) => {
  const i = r.lastIndexOf("!");
  const sheet = r.slice(0, i).replace(/^'(.*)'$/, "$1").replace(/''/g, "'");
  return `${sheet}!${r.slice(i + 1).replace(/\$/g, "").toUpperCase()}`;
};

export function readXlsx(buf: ArrayBuffer): Book {
  // sheetStubs keeps formula cells that have no cached value (files not saved by Excel);
  // cellStyles is what makes SheetJS read column widths
  const wb = XLSX.read(buf, { cellFormula: true, cellNF: true, sheetStubs: true, cellStyles: true });
  const data: Record<string, RawCellContent[][]> = {};
  const formats = new Map<string, string>();
  const pre: Omit<SheetMeta, "id">[] = [];

  for (const name of wb.SheetNames) {
    const ws = wb.Sheets[name];
    const range = ws["!ref"] ? XLSX.utils.decode_range(ws["!ref"]) : null;
    const rows = range ? range.e.r + 1 : 0;
    const cols = range ? range.e.c + 1 : 0;
    const grid: RawCellContent[][] = Array.from({ length: rows }, () => Array(cols).fill(null));

    for (const key of Object.keys(ws)) {
      if (key.startsWith("!")) continue;
      const cell = ws[key] as XLSX.CellObject;
      const { r, c } = XLSX.utils.decode_cell(key);
      if (r >= rows || c >= cols) continue;
      grid[r][c] = toRaw(cell);
      if (cell.z && cell.z !== "General") formats.set(ref(name, r, c), String(cell.z));
    }

    // sized in characters: our mono digits run wider than Excel's Calibri
    const colWidths = (ws["!cols"] ?? []).map((ci) => {
      const chars = ci?.wch ?? ci?.width;
      return chars ? Math.round(chars * 7.5 + 12) : undefined;
    });
    data[name] = grid;
    pre.push({ name, rows, cols, colWidths });
  }

  const hf = HyperFormula.buildFromSheets(data, { licenseKey: "gpl-v3" });
  const sheets = pre.map((s) => ({ ...s, id: hf.getSheetId(s.name)! }));
  const saved = wb.Props?.ModifiedDate;
  const modified = saved instanceof Date && !isNaN(saved.getTime()) ? saved.toISOString() : null;
  return { hf, sheets, formats, modified };
}

function toRaw(cell: XLSX.CellObject): RawCellContent {
  if (cell.f) return `=${cell.f}`;
  switch (cell.t) {
    case "n":
    case "b":
      return cell.v as number | boolean;
    case "s":
      return typeof cell.v === "string" && cell.v.startsWith("=") ? `'${cell.v}` : (cell.v as string);
    case "d":
      return cell.v instanceof Date ? cell.v.toISOString().slice(0, 10) : null;
    default:
      return null;
  }
}

export function view(book: Book, sheet: SheetMeta, row: number, col: number): CellView {
  const addr: SimpleCellAddress = { sheet: sheet.id, row, col };
  const v = book.hf.getCellValue(addr);
  const formula = book.hf.doesCellHaveFormula(addr);

  if (v instanceof DetailedCellError) return { text: v.value, kind: "error", formula, input: false };
  if (v === null || v === "") return { text: "", kind: "empty", formula, input: false };
  if (typeof v === "boolean") return { text: v ? "TRUE" : "FALSE", kind: "bool", formula, input: false };
  if (typeof v === "string") return { text: v, kind: "text", formula, input: false };

  const fmt = book.formats.get(ref(sheet.name, row, col)) ?? "General";
  let text: string;
  try {
    text = XLSX.SSF.format(fmt, v);
  } catch {
    text = XLSX.SSF.format("General", v);
  }
  return { text, kind: "number", formula, input: !formula };
}

/** What the formula bar shows and what editing starts from. */
export function raw(book: Book, sheet: SheetMeta, row: number, col: number): string {
  const addr = { sheet: sheet.id, row, col };
  const f = book.hf.getCellFormula(addr);
  if (f) return f;
  const v = book.hf.getCellSerialized(addr);
  return v === null || v === undefined ? "" : String(v);
}

export function write(book: Book, sheet: SheetMeta, row: number, col: number, text: string) {
  const { value, format } = parseInput(text);
  const key = ref(sheet.name, row, col);
  if (format && !book.formats.has(key)) book.formats.set(key, format);
  book.hf.setCellContents({ sheet: sheet.id, row, col }, [[value]]);
}

function parseInput(text: string): { value: RawCellContent; format?: string } {
  const t = text.trim();
  if (t === "") return { value: null };
  if (t.startsWith("=")) return { value: t };
  if (/^(true|false)$/i.test(t)) return { value: t.toUpperCase() === "TRUE" };

  const pct = t.match(/^(-?[\d,]*\.?\d+)%$/);
  if (pct) return { value: Number(pct[1].replace(/,/g, "")) / 100, format: "0.00%" };

  const neg = /^\(.*\)$/.test(t);
  const num = t.replace(/^\((.*)\)$/, "$1").replace(/[$,\s]/g, "");
  if (/^-?\d*\.?\d+(e[+-]?\d+)?$/i.test(num)) return { value: (neg ? -1 : 1) * Number(num) };

  return { value: text };
}

export const FORMATS: { label: string; example: string; fmt: string }[] = [
  { label: "Automatic", example: "1234.5", fmt: "General" },
  { label: "Number", example: "1,234.50", fmt: "#,##0.00;(#,##0.00)" },
  { label: "Accounting", example: "$(1,234)", fmt: '$#,##0;($#,##0);"-"' },
  { label: "Percent", example: "3.50%", fmt: "0.00%" },
  { label: "Rate", example: "1.0842", fmt: "0.0000" },
];

export function getFormat(book: Book, sheet: SheetMeta, row: number, col: number): string {
  return book.formats.get(ref(sheet.name, row, col)) ?? "General";
}

export function setFormat(book: Book, sheet: SheetMeta, row: number, col: number, fmt: string) {
  const key = ref(sheet.name, row, col);
  if (fmt === "General") book.formats.delete(key);
  else book.formats.set(key, fmt);
}

/** Add or remove one decimal place in every section of a number format. */
export function shiftDecimals(fmt: string, delta: 1 | -1): string {
  const base = fmt === "General" ? "0" : fmt;
  return base
    .split(";")
    .map((section) =>
      section.replace(/0(\.(0+))?(?!.*0)/, (_m, _d, zeros: string | undefined) => {
        const n = Math.max(0, (zeros?.length ?? 0) + delta);
        return n === 0 ? "0" : `0.${"0".repeat(n)}`;
      }),
    )
    .join(";");
}

/* ---------- updating a constant to its live value ---------- */

const sheetOf = (book: Book, name: string) => book.sheets.find((s) => s.name === name);

export type CellUpdate = { cell: string; text: string };

/** The writes that move `model` to `live`: the new number for an input cell, or, for a
 *  number buried in a formula, the literal swapped in that cell and in the neighbours on
 *  its row that repeat it (the same formula copied across the years). */
export function liveUpdates(book: Book, cell: string, model: number, live: number): CellUpdate[] {
  const { sheet: name, row, col } = parseRef(cell);
  const sheet = sheetOf(book, name);
  if (!sheet) return [];
  const here = raw(book, sheet, row, col);
  if (!here.startsWith("=")) return [{ cell, text: String(live) }];

  const literal = new RegExp(`(?<![\\w.])${String(model).replace(".", "\\.")}(?![\\d.])`);
  const swap = (c: number) => {
    const f = raw(book, sheet, row, c);
    return f.startsWith("=") && literal.test(f) ? { cell: ref(name, row, c), text: f.replace(literal, String(live)) } : null;
  };
  const out: CellUpdate[] = [];
  for (let c = col; c >= 0; c--) {
    const u = swap(c);
    if (!u) break;
    out.unshift(u);
  }
  for (let c = col + 1; c < sheet.cols; c++) {
    const u = swap(c);
    if (!u) break;
    out.push(u);
  }
  return out;
}

export function writeRef(book: Book, cell: string, text: string) {
  const { sheet: name, row, col } = parseRef(cell);
  const sheet = sheetOf(book, name);
  if (sheet) write(book, sheet, row, col, text);
}

export function numberAt(hf: HyperFormula, cell: string): number | null {
  const { sheet: name, row, col } = parseRef(cell);
  const id = hf.getSheetId(name);
  if (id === undefined) return null;
  const v = hf.getCellValue({ sheet: id, row, col });
  return typeof v === "number" ? v : null;
}

/** Outputs before and after the updates, computed on a throwaway copy of the book. */
export function whatIf(book: Book, updates: CellUpdate[], outputs: string[]) {
  const copy = HyperFormula.buildFromSheets(book.hf.getAllSheetsSerialized(), { licenseKey: "gpl-v3" });
  try {
    const before = outputs.map((o) => numberAt(copy, o));
    for (const u of updates) {
      const { sheet: name, row, col } = parseRef(u.cell);
      const id = copy.getSheetId(name);
      if (id !== undefined) copy.setCellContents({ sheet: id, row, col }, [[parseInput(u.text).value]]);
    }
    return outputs.map((o, i) => ({ output: o, before: before[i], after: numberAt(copy, o) }));
  } finally {
    copy.destroy();
  }
}

export function rawRef(book: Book, cell: string): string {
  const { sheet: name, row, col } = parseRef(cell);
  const sheet = sheetOf(book, name);
  return sheet ? raw(book, sheet, row, col) : "";
}

/* ---------- sheets ---------- */

/** Move format keys from one sheet name to another (or drop them when `to` is null). */
function rekeyFormats(book: Book, from: string, to: string | null) {
  for (const key of [...book.formats.keys()]) {
    if (!key.startsWith(`${from}!`)) continue;
    const fmt = book.formats.get(key)!;
    book.formats.delete(key);
    if (to !== null) book.formats.set(`${to}!${key.slice(from.length + 1)}`, fmt);
  }
}

/** Adds a blank "Sheet N" at the end and returns its index. */
export function addSheet(book: Book): number {
  let n = book.sheets.length + 1;
  while (!book.hf.isItPossibleToAddSheet(`Sheet${n}`)) n++;
  const name = book.hf.addSheet(`Sheet${n}`);
  book.sheets.push({ id: book.hf.getSheetId(name)!, name, rows: 0, cols: 0, colWidths: [] });
  return book.sheets.length - 1;
}

/** Renames a sheet; formulas that point at it follow. Returns false if the name is taken or invalid. */
export function renameSheet(book: Book, ix: number, name: string): boolean {
  const sheet = book.sheets[ix];
  const next = name.trim();
  if (!sheet || !next || next === sheet.name) return false;
  if (!book.hf.isItPossibleToRenameSheet(sheet.id, next)) return false;
  book.hf.renameSheet(sheet.id, next);
  rekeyFormats(book, sheet.name, next);
  sheet.name = next;
  return true;
}

export function removeSheet(book: Book, ix: number) {
  const sheet = book.sheets[ix];
  if (!sheet || book.sheets.length < 2) return;
  book.hf.removeSheet(sheet.id);
  syncSheets(book);
}

/** Sheets that left the engine, kept so undo brings each back where it was, as it was:
 *  the engine restores the cells, but not the tab's place, column widths or number formats. */
type Gone = { meta: SheetMeta; ix: number; formats: [string, string][] };
const goneSheets = new WeakMap<Book, Map<number, Gone>>();

/**
 * Insert (count > 0) or delete (count < 0) whole rows or columns at `at`. Formulas that
 * point past them follow; formats and column widths move with their cells.
 */
export function shiftLines(book: Book, sheet: SheetMeta, axis: "row" | "col", at: number, count: number) {
  const span: [number, number] = [at, Math.abs(count)];
  const hf = book.hf;
  if (axis === "row") {
    if (count > 0 ? !hf.isItPossibleToAddRows(sheet.id, span) : !hf.isItPossibleToRemoveRows(sheet.id, span)) return false;
    count > 0 ? hf.addRows(sheet.id, span) : hf.removeRows(sheet.id, span);
  } else {
    if (count > 0 ? !hf.isItPossibleToAddColumns(sheet.id, span) : !hf.isItPossibleToRemoveColumns(sheet.id, span)) return false;
    count > 0 ? hf.addColumns(sheet.id, span) : hf.removeColumns(sheet.id, span);
    if (count > 0) sheet.colWidths.splice(at, 0, ...Array(count).fill(undefined));
    else sheet.colWidths.splice(at, -count);
  }

  const moved = new Map<string, string>();
  for (const [key, fmt] of book.formats) {
    if (!key.startsWith(`${sheet.name}!`)) continue;
    book.formats.delete(key);
    const { row, col } = parseRef(key);
    const n = axis === "row" ? row : col;
    if (count < 0 && n >= at && n < at - count) continue; // deleted
    const shifted = n >= at ? n + count : n;
    moved.set(axis === "row" ? ref(sheet.name, shifted, col) : ref(sheet.name, row, shifted), fmt);
  }
  for (const [key, fmt] of moved) book.formats.set(key, fmt);

  const key = axis === "row" ? "rows" : "cols";
  if (at < sheet[key]) sheet[key] = Math.max(at, sheet[key] + count);
  return true;
}

/** After undo/redo, which can add, remove or rename sheets, match `book.sheets` to the engine. */
export function syncSheets(book: Book) {
  const gone = goneSheets.get(book) ?? new Map<number, Gone>();
  goneSheets.set(book, gone);
  const live = new Set(book.hf.getSheetNames().map((name) => book.hf.getSheetId(name)!));
  book.sheets.forEach((meta, ix) => {
    if (live.has(meta.id)) return;
    const prefix = `${meta.name}!`;
    const formats = [...book.formats].filter(([key]) => key.startsWith(prefix));
    gone.set(meta.id, { meta, ix, formats });
    rekeyFormats(book, meta.name, null);
  });

  const byId = new Map(book.sheets.map((s) => [s.id, s]));
  const next = book.hf.getSheetNames().map((name) => {
    const id = book.hf.getSheetId(name)!;
    const meta = byId.get(id);
    if (!meta) return { id, name, rows: 0, cols: 0, colWidths: [] };
    if (meta.name !== name) {
      rekeyFormats(book, meta.name, name);
      meta.name = name;
    }
    return meta;
  });
  // the engine lists a sheet it brought back last; put it back in its old place, with its formats
  const kept = next.filter((m) => byId.has(m.id));
  for (const m of next.filter((m) => !byId.has(m.id))) {
    const was = gone.get(m.id);
    gone.delete(m.id);
    if (!was || was.meta.name !== m.name) {
      kept.push(m);
      continue;
    }
    for (const [key, fmt] of was.formats) book.formats.set(key, fmt);
    kept.splice(Math.min(was.ix, kept.length), 0, was.meta);
  }
  book.sheets.splice(0, book.sheets.length, ...kept);
}

/* ---------- export ---------- */

/** The workbook as it stands (edits, updates and added sheets included) as .xlsx bytes.
 *  Formulas keep their current values so Excel shows numbers before recalculating. */
export function xlsxBytes(book: Book): ArrayBuffer {
  const wb = XLSX.utils.book_new();
  for (const sheet of book.sheets) {
    const data = book.hf.getSheetSerialized(sheet.id);
    const ws: XLSX.WorkSheet = {};
    let maxR = 0;
    let maxC = 0;
    data.forEach((row, r) =>
      row.forEach((content, c) => {
        if (content === null || content === undefined || content === "") return;
        const addr = { sheet: sheet.id, row: r, col: c };
        const value = book.hf.getCellValue(addr);
        const cell: XLSX.CellObject = { t: "z" };
        if (typeof content === "string" && content.startsWith("=")) cell.f = content.slice(1);
        if (typeof value === "number") Object.assign(cell, { t: "n", v: value });
        else if (typeof value === "boolean") Object.assign(cell, { t: "b", v: value });
        else if (value instanceof DetailedCellError) Object.assign(cell, { t: "e", v: 0x17, w: value.value });
        else if (value !== null && value !== "") Object.assign(cell, { t: "s", v: String(value) });
        const fmt = book.formats.get(ref(sheet.name, r, c));
        if (fmt) cell.z = fmt;
        ws[XLSX.utils.encode_cell({ r, c })] = cell;
        maxR = Math.max(maxR, r);
        maxC = Math.max(maxC, c);
      }),
    );
    ws["!ref"] = XLSX.utils.encode_range({ s: { r: 0, c: 0 }, e: { r: maxR, c: maxC } });
    // back from px to Excel character widths (inverse of readXlsx)
    ws["!cols"] = sheet.colWidths.map((px) => (px ? { wch: Math.max(1, Math.round((px - 12) / 7.5)) } : {}));
    XLSX.utils.book_append_sheet(wb, ws, sheet.name);
  }
  return XLSX.write(wb, { type: "array", bookType: "xlsx" });
}

export const xlsxName = (filename: string) =>
  /\.xlsx$/i.test(filename) ? filename : `${filename.replace(/\.(xlsm|xls)$/i, "")}.xlsx`;

export function downloadXlsx(book: Book, filename: string) {
  const url = URL.createObjectURL(new Blob([xlsxBytes(book)]));
  const a = Object.assign(document.createElement("a"), { href: url, download: xlsxName(filename) });
  a.click();
  URL.revokeObjectURL(url);
}

/** A new, empty workbook with one sheet. */
export function blankBook(): Book {
  const hf = HyperFormula.buildFromSheets({ Sheet1: [] }, { licenseKey: "gpl-v3" });
  return { hf, sheets: [{ id: hf.getSheetId("Sheet1")!, name: "Sheet1", rows: 0, cols: 0, colWidths: [] }], formats: new Map(), modified: null };
}

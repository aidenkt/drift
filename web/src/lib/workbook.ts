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
  return { hf, sheets, formats };
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

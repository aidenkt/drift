// Spreadsheet clipboard helpers: TSV in and out (as Excel and Google Sheets write it),
// and moving a formula's relative references when it's pasted somewhere else.

/** Rows of cells → TSV. Cells holding tabs, newlines or quotes are quoted, like Excel does. */
export function toTsv(rows: string[][]): string {
  const cell = (t: string) => (/[\t\n\r"]/.test(t) ? `"${t.replace(/"/g, '""')}"` : t);
  return rows.map((r) => r.map(cell).join("\t")).join("\n");
}

/** TSV → rows of cells. Handles quoted cells and the trailing newline Excel adds. */
export function fromTsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let cur = "";
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') (cur += '"'), i++;
      else if (ch === '"') quoted = false;
      else cur += ch;
    } else if (ch === '"' && cur === "") quoted = true;
    else if (ch === "\t") row.push(cur), (cur = "");
    else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && text[i + 1] === "\n") i++;
      row.push(cur), rows.push(row), (row = []), (cur = "");
    } else cur += ch;
  }
  if (cur !== "" || row.length) row.push(cur), rows.push(row);
  return rows;
}

/** HTML table for apps that prefer it (Docs, Notion, Excel keeps cell boundaries either way). */
export function toHtml(rows: string[][]): string {
  const esc = (t: string) => t.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  return `<table>${rows.map((r) => `<tr>${r.map((c) => `<td>${esc(c)}</td>`).join("")}</tr>`).join("")}</table>`;
}

const colNum = (letters: string) => [...letters].reduce((n, ch) => n * 26 + ch.charCodeAt(0) - 64, 0) - 1;
const colLetters = (n: number) => {
  let s = "";
  for (n += 1; n > 0; n = Math.floor((n - 1) / 26)) s = String.fromCharCode(65 + ((n - 1) % 26)) + s;
  return s;
};

/**
 * Shift the relative references in a formula by (dr, dc), leaving $-anchored parts alone,
 * as Excel does when a formula is pasted. References pushed off the sheet become #REF!.
 * String literals and quoted sheet names are skipped.
 */
export function shiftFormula(formula: string, dr: number, dc: number): string {
  if (!formula.startsWith("=") || (dr === 0 && dc === 0)) return formula;
  let out = "";
  let i = 0;
  const ref = /^(\$?)([A-Z]{1,3})(\$?)(\d+)(?![A-Za-z0-9_(])/;
  while (i < formula.length) {
    const ch = formula[i];
    // copy literals through untouched
    if (ch === '"' || ch === "'") {
      let j = i + 1;
      while (j < formula.length && !(formula[j] === ch && formula[j + 1] !== ch)) j += formula[j] === ch ? 2 : 1;
      out += formula.slice(i, j + 1);
      i = j + 1;
      continue;
    }
    const prev = formula[i - 1] ?? "";
    const m = /[A-Za-z0-9_.]/.test(prev) ? null : formula.slice(i).match(ref);
    if (m) {
      const [whole, colAbs, col, rowAbs, row] = m;
      const c = colAbs ? colNum(col) : colNum(col) + dc;
      const r = rowAbs ? Number(row) - 1 : Number(row) - 1 + dr;
      out += c < 0 || r < 0 ? "#REF!" : `${colAbs}${colLetters(c)}${rowAbs}${r + 1}`;
      i += whole.length;
      continue;
    }
    out += ch;
    i++;
  }
  return out;
}

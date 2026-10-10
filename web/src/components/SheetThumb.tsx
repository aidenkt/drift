import { useMemo } from "react";
import { normalizeRef, ref, view, type Book } from "../lib/workbook";
import type { Report } from "../types";

const ROWS = 16;
const COLS = 6;

/** A workbook's busiest sheet, drawn small: the sheet with the most stale constants when the
 *  model has been checked (scrolled so they show), otherwise the top of the first sheet.
 *  It fills the card edge to edge, like a picture of the sheet. */
export default function SheetThumb({ book, report }: { book: Book; report: Report | null }) {
  const { sheet, stale, top } = useMemo(() => {
    const stale = new Set(
      (report?.constants ?? []).filter((c) => c.check?.status === "stale").map((c) => normalizeRef(c.cell)),
    );
    const count = (name: string) => [...stale].filter((c) => c.startsWith(`${name}!`)).length;
    const sheets = book.sheets.filter((s) => s.rows > 0);
    const sheet = [...sheets].sort((a, b) => count(b.name) - count(a.name))[0] ?? book.sheets[0];
    const rows = [...stale].filter((c) => sheet && c.startsWith(`${sheet.name}!`)).map((c) => Number(c.match(/(\d+)$/)![1]) - 1);
    const top = rows.length ? Math.max(0, Math.max(...rows) - ROWS + 3) : 0;
    return { sheet, stale, top };
  }, [book, report]);

  if (!sheet) return <div className="thumb" />;
  const cols = Math.min(Math.max(sheet.cols, 4), COLS);
  // columns keep their proportions but share the card's width
  const widths = Array.from({ length: cols }, (_, c) => sheet.colWidths[c] ?? 72);
  const total = widths.reduce((a, b) => a + b, 0);

  return (
    <div className="thumb" aria-hidden>
      <table>
        <colgroup>
          {widths.map((w, c) => (
            <col key={c} style={{ width: `${((w / total) * 100).toFixed(1)}%` }} />
          ))}
        </colgroup>
        <tbody>
          {Array.from({ length: ROWS }, (_, i) => top + i).map((r) => (
            <tr key={r}>
              {Array.from({ length: cols }, (_, c) => {
                const v = view(book, sheet, r, c);
                const isStale = stale.has(ref(sheet.name, r, c));
                const cls = [v.kind === "number" && "n", v.input && "in", isStale && "stale"].filter(Boolean).join(" ");
                return (
                  <td key={c} className={cls || undefined}>
                    {v.text}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

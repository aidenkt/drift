import { parseRef, ref } from "./workbook";

/** Where the app is, in the path: "/" for all models, "/m/<key>/<sheet>/<cell>" for an open one. */
export type Route = { key: string; cell?: string } | null;

const PATH = /^\/m\/([^/]+)(?:\/([^/]+)\/([A-Za-z]+\d+))?\/?$/;

export function readRoute(path = location.pathname): Route {
  const m = path.match(PATH);
  if (!m) return null;
  const key = decodeURIComponent(m[1]);
  return m[2] ? { key, cell: `${decodeURIComponent(m[2])}!${m[3].toUpperCase()}` } : { key };
}

/** "model:case-study" + "P&L!C18" -> "/m/model:case-study/P%26L/C18" */
export function modelPath(key: string, cell?: string): string {
  const base = `/m/${encodeURIComponent(key).replace(/%3A/gi, ":")}`;
  if (!cell) return base;
  const { sheet, row, col } = parseRef(cell);
  return `${base}/${encodeURIComponent(sheet)}/${ref("", row, col).slice(1)}`;
}

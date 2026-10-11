import { parseRef, type Book } from "./workbook";

/** Where the app is, in the path: "/" for all models, "/m/<id>/<sheet>/<cell>" for an open one,
 *  e.g. /m/case-study/pl/C18. The sheet and cell are left off when they'd be the first sheet's A1. */
export type Route = { id: string; sheet?: string; cell?: string } | null;

const PATH = /^\/m\/([a-z0-9-]+)(?:\/([a-z0-9-]+)(?:\/([a-z]+\d+))?)?\/?$/i;

/** A model's short id: "model:case-study" -> "case-study", "file:1791679148294" -> "mv3302et", "doc:abc" -> "abc". */
export function routeId(key: string): string {
  const [kind, rest] = [key.slice(0, key.indexOf(":")), key.slice(key.indexOf(":") + 1)];
  return kind === "file" && /^\d+$/.test(rest) ? Number(rest).toString(36) : rest.toLowerCase().replace(/[^a-z0-9-]+/g, "-");
}

/** "P&L" -> "pl", "Cash Flow" -> "cash-flow" */
export const sheetSlug = (name: string) =>
  name.toLowerCase().replace(/&/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "sheet";

export function readRoute(path = location.pathname): Route {
  const m = path.match(PATH);
  if (!m) return null;
  return { id: m[1].toLowerCase(), sheet: m[2]?.toLowerCase(), cell: m[3]?.toUpperCase() };
}

/** The cell a route points at in this workbook, as "P&L!C18"; none if it names no sheet here. */
export function routeCell(route: NonNullable<Route>, book: Book): string | undefined {
  if (!route.sheet) return undefined;
  const sheet = book.sheets.find((s) => sheetSlug(s.name) === route.sheet);
  return sheet ? `${sheet.name}!${route.cell ?? "A1"}` : undefined;
}

export function modelPath(key: string, cell?: string, book?: Book): string {
  const base = `/m/${routeId(key)}`;
  if (!cell) return base;
  const { sheet } = parseRef(cell);
  const addr = cell.slice(cell.lastIndexOf("!") + 1).replace(/\$/g, "").toUpperCase();
  const first = book?.sheets[0]?.name === sheet;
  if (addr === "A1") return first ? base : `${base}/${sheetSlug(sheet)}`;
  return `${base}/${sheetSlug(sheet)}/${addr}`;
}

// Date phrases inside a search: "oct 8", "10/8", "2026-10", "last week",
// "3 days ago", "after:oct 1", "<sep 15". Everything else stays a text term.

/** Inclusive range of ISO days; "" means open-ended. */
export type DateRange = { from: string; to: string; label: string };
export type ParsedQuery = { terms: string[]; ranges: DateRange[] };

const MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"];
const OPS: Record<string, "before" | "after" | "since" | "until" | "on"> = {
  before: "before",
  "<": "before",
  after: "after",
  ">": "after",
  since: "since",
  from: "since",
  ">=": "since",
  until: "until",
  "<=": "until",
  on: "on",
};

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const addDays = (d: Date, n: number) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
const fmt = (d: Date, year = false) =>
  d.toLocaleDateString("en-US", { month: "short", day: "numeric", ...(year ? { year: "numeric" } : {}) });

/** "oct", "sept", "october" -> 0-based month; needs at least three letters. */
function monthOf(word: string): number | null {
  if (word.length < 3) return null;
  const i = MONTHS.findIndex((m) => m.startsWith(word));
  return i < 0 ? null : i;
}

/** A day with no year means the most recent one, so "dec 20" in October is last December. */
function recent(today: Date, m: number, d: number): Date {
  const date = new Date(today.getFullYear(), m, d);
  return date > today ? new Date(today.getFullYear() - 1, m, d) : date;
}

type Span = { start: Date; end: Date; label: string };

function day(d: Date, label = fmt(d)): Span {
  return { start: d, end: d, label };
}

/** Read one date phrase starting at tokens[i]; returns the span and how many tokens it used. */
function readDate(tokens: string[], i: number, today: Date): { span: Span; used: number } | null {
  const [a, b, c] = [tokens[i], tokens[i + 1], tokens[i + 2]];
  const year = (s?: string) => (s && /^\d{4}$/.test(s) ? Number(s) : null);
  const dom = (s?: string) => (s && /^\d{1,2}(st|nd|rd|th)?,?$/.test(s) ? parseInt(s, 10) : null);

  if (a === "today") return { span: day(today, "today"), used: 1 };
  if (a === "yesterday") return { span: day(addDays(today, -1), "yesterday"), used: 1 };

  // this/last week, month, year
  if ((a === "this" || a === "last") && (b === "week" || b === "month" || b === "year")) {
    const back = a === "last" ? 1 : 0;
    if (b === "week") {
      const monday = addDays(today, -((today.getDay() + 6) % 7) - 7 * back);
      return { span: { start: monday, end: back ? addDays(monday, 6) : today, label: `${a} week` }, used: 2 };
    }
    if (b === "month") {
      const start = new Date(today.getFullYear(), today.getMonth() - back, 1);
      const end = back ? new Date(today.getFullYear(), today.getMonth(), 0) : today;
      return { span: { start, end, label: `${a} month` }, used: 2 };
    }
    const start = new Date(today.getFullYear() - back, 0, 1);
    const end = back ? new Date(today.getFullYear() - 1, 11, 31) : today;
    return { span: { start, end, label: `${a} year` }, used: 2 };
  }

  // last 7 days, past 2 weeks
  if ((a === "last" || a === "past") && b && /^\d+$/.test(b) && c && /^(days?|weeks?|months?)$/.test(c)) {
    const n = Number(b) * (c.startsWith("week") ? 7 : c.startsWith("month") ? 30 : 1);
    return { span: { start: addDays(today, -n + 1), end: today, label: `last ${b} ${c}` }, used: 3 };
  }

  // 3 days ago, 2 weeks ago: the same rounding the list shows
  if (a && /^\d+$/.test(a) && b && /^(days?|weeks?|months?)$/.test(b) && c === "ago") {
    const n = Number(a);
    const span = b.startsWith("day") ? [n, n] : b.startsWith("week") ? [7 * n - 3, 7 * n + 3] : [30 * n - 15, 30 * n + 14];
    return { span: { start: addDays(today, -span[1]), end: addDays(today, -span[0]), label: `${a} ${b} ago` }, used: 3 };
  }

  // 2026-10-08, 2026-10, 2026
  let m = a?.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
  if (m) return { span: day(new Date(+m[1], +m[2] - 1, +m[3]), fmt(new Date(+m[1], +m[2] - 1, +m[3]), true)), used: 1 };
  m = a?.match(/^(\d{4})-(\d{1,2})$/);
  if (m) {
    const start = new Date(+m[1], +m[2] - 1, 1);
    return { span: { start, end: new Date(+m[1], +m[2], 0), label: start.toLocaleDateString("en-US", { month: "short", year: "numeric" }) }, used: 1 };
  }
  if (a && /^(19|20)\d{2}$/.test(a)) {
    return { span: { start: new Date(+a, 0, 1), end: new Date(+a, 11, 31), label: a }, used: 1 };
  }

  // 10/8, 10/8/26, 10/08/2026
  m = a?.match(/^(\d{1,2})\/(\d{1,2})(?:\/(\d{2}|\d{4}))?$/);
  if (m) {
    const y = m[3] ? (m[3].length === 2 ? 2000 + +m[3] : +m[3]) : null;
    const d = y ? new Date(y, +m[1] - 1, +m[2]) : recent(today, +m[1] - 1, +m[2]);
    return { span: day(d, fmt(d, !!y)), used: 1 };
  }

  // oct, oct 8, october 8 2026, oct 2026, 8 oct
  const mo = a ? monthOf(a.replace(/[.,]$/, "")) : null;
  if (mo != null) {
    const d = dom(b);
    if (d) {
      const y = year(c);
      const date = y ? new Date(y, mo, d) : recent(today, mo, d);
      return { span: day(date, fmt(date, !!y)), used: y ? 3 : 2 };
    }
    const y = year(b) ?? (mo > today.getMonth() ? today.getFullYear() - 1 : today.getFullYear());
    const start = new Date(y, mo, 1);
    return {
      span: { start, end: new Date(y, mo + 1, 0), label: start.toLocaleDateString("en-US", { month: "long", ...(year(b) ? { year: "numeric" } : {}) }) },
      used: year(b) ? 2 : 1,
    };
  }
  const d = dom(a);
  const mo2 = b ? monthOf(b) : null;
  if (d && mo2 != null) {
    const y = year(c);
    const date = y ? new Date(y, mo2, d) : recent(today, mo2, d);
    return { span: day(date, fmt(date, !!y)), used: y ? 3 : 2 };
  }
  return null;
}

/** Split a search into date ranges and the leftover text terms. */
export function parseQuery(query: string, now = new Date()): ParsedQuery {
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  // "after:oct" and ">oct" both become ["after", "oct"]
  const tokens = query
    .toLowerCase()
    .replace(/\b(before|after|since|from|until|on):/g, " $1: ")
    .replace(/(^|\s)(>=|<=|>|<)/g, " $2 ")
    .split(/\s+/)
    .map((t) => t.replace(/:$/, ""))
    .filter(Boolean);

  const terms: string[] = [];
  const ranges: DateRange[] = [];
  for (let i = 0; i < tokens.length; ) {
    const op = OPS[tokens[i]];
    const at = op ? i + 1 : i;
    const found = readDate(tokens, at, today);
    if (!found) {
      // a bare "on" or "from" is ordinary text
      terms.push(tokens[i]);
      i += 1;
      continue;
    }
    const { start, end, label } = found.span;
    const range =
      op === "before" ? { from: "", to: iso(addDays(start, -1)), label: `before ${label}` }
      : op === "after" ? { from: iso(addDays(end, 1)), to: "", label: `after ${label}` }
      : op === "since" ? { from: iso(start), to: "", label: `since ${label}` }
      : op === "until" ? { from: "", to: iso(end), label: `until ${label}` }
      : { from: iso(start), to: iso(end), label };
    ranges.push(range);
    i = at + found.used;
  }
  return { terms, ranges };
}

export function inRange(date: string, r: DateRange): boolean {
  const d = date.slice(0, 10);
  return (!r.from || d >= r.from) && (!r.to || d <= r.to);
}

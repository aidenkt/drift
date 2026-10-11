/** A checked model's report as timeline events: one per assumption the engine checked.
 *  Only what the report says: no titles, numbers or sources of our own. */

import type { Signal, Source, TimelineEvent } from "../data/timeline";
import type { Check, Constant, Report } from "../types";
import { MINUS, value } from "./format";

const STATUS = { stale: "stale", current: "current", unknown: "watching" } as const;

const host = (url: string) => {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return null;
  }
};

// "%" shows a fraction as a percentage, so it needs both: a label that says percent and a
// value stored as a fraction. Anything else stays as the model holds it; the label names its unit.
const unitOf = (c: Constant, live: number | null) =>
  (c.label ?? "").includes("%") && Math.abs(c.value) <= 1 && Math.abs(live ?? 0) <= 1 ? "%" : "";

const signed = (pct: number) => `${pct > 0 ? "+" : pct < 0 ? MINUS : ""}${Math.abs(pct).toFixed(1)}%`;

/** The pages behind the check: what the live value was read from, then the news around it. */
function sourcesOf(k: Check, liveText: string | null): Source[] {
  const cited = [
    ...(k.evidence ?? []).map((e) => ({ ...e, title: e.quote })),
    ...(k.events ?? []).map((e) => ({ ...e, title: e.summary })),
  ];
  const seen = new Set<string>();
  let valued = false;
  return cited.flatMap((s): Source[] => {
    const site = host(s.url ?? "");
    const url = site ? s.url : "";
    const publisher = s.publisher ?? site ?? "";
    const title = s.title || publisher;
    // the same passage cited twice is one card; title + url is also the card's key
    const keys = [`${url}\n${s.quote}`, title + url];
    if (keys.some((key) => seen.has(key))) return [];
    keys.forEach((key) => seen.add(key));
    // the live value belongs to the page the check names as its source
    const gives = !valued && !!url && url === k.source_url ? liveText : null;
    if (gives) valued = true;
    return [
      {
        publisher,
        title,
        url,
        date: s.date ?? "",
        via: site === "fred.stlouisfed.org" ? "FRED" : "Bright Data",
        quote: s.quote,
        ...(gives ? { value: gives } : {}),
        ...(s.image ? { image: s.image } : {}),
      },
    ];
  });
}

/** The checker's own sentences: what the value should be and what that does are findings,
 *  next steps are still to do. */
function signalsOf(c: Constant, k: Check): Signal[] {
  const said: Signal[] = [
    { look_for: k.assumption ?? "", observed: "", met: true },
    { look_for: k.prediction ?? "", observed: "", met: true },
    ...(k.next_steps ?? []).map((step) => ({ look_for: step, observed: "", met: false })),
  ];
  if (c.embedded && c.formula) said.push({ look_for: "Number is buried in a formula, not an input cell", observed: c.formula, met: true });
  return said.filter((s, i) => s.look_for && said.findIndex((x) => x.look_for === s.look_for) === i);
}

// More numbers than this still being read (a fresh upload) show as placeholder rows, not one row each.
const FEW = 5;

const pending = (c: Constant) => c.stage === "labeling" || c.stage === "checking";

/** How many numbers the engine is still reading, when there are too many to list one by one. */
export function reading(report: Report | null | undefined): number {
  const n = (report?.constants ?? []).filter((c) => c.stage === "labeling").length;
  return n > FEW ? n : 0;
}

/** A number the engine is still labeling or checking: its name so far and the value in the model. */
function checkingEvent(report: Report, c: Constant): TimelineEvent {
  const label = c.label || c.cell;
  return {
    id: c.literal_index != null ? `${c.cell}#${c.literal_index}` : c.cell,
    date: report.checked_on,
    title: label.replace(/\s*\([^()]*\)$/, ""),
    kind: "news",
    status: "checking",
    cells: c.cells?.length ? c.cells : [c.cell.split(":")[0]],
    driver: c.driver ?? null,
    state: { label, unit: unitOf(c, null), model: c.value, live: null, change: null, as_of: "", history: [] },
    signals: [],
    sources: [],
    impact: [],
  };
}

export function eventsFromReport(report: Report): TimelineEvent[] {
  const labels = new Map((report.outputs ?? []).map((o) => [o.cell, o.label]));
  const listed = reading(report) === 0;
  const events = (report.constants ?? []).flatMap((c): TimelineEvent[] => {
    // still being read or checked: shown now under its temporary name, filled in when its check lands
    if (pending(c)) return c.stage === "checking" || listed ? [checkingEvent(report, c)] : [];
    const k = c.check;
    if (!k) return [];
    const live = k.live ?? null;
    const unit = unitOf(c, live);
    const as_of = (k.as_of ?? report.checked_on ?? "").slice(0, 10);
    const change = k.drift_pct != null ? signed(k.drift_pct) : null;
    const label = c.label || c.cell;
    // the unit in brackets stays on the label; the title reads better without it
    const name = label.replace(/\s*\([^()]*\)$/, "");
    return [
      {
        // two numbers in one formula share their cells and differ by which literal they are
        id: c.literal_index != null ? `${c.cell}#${c.literal_index}` : c.cell,
        date: as_of,
        title: k.drift_pct ? `${name} ${k.drift_pct > 0 ? "up" : "down"} ${Math.abs(k.drift_pct).toFixed(1)}%` : name,
        kind: live != null ? "drift" : "news",
        status: STATUS[k.status] ?? "watching",
        // a grouped constant's own cell is a range, which the grid can't open
        cells: c.cells?.length ? c.cells : [c.cell.split(":")[0]],
        driver: c.driver ?? null,
        state: {
          label,
          unit,
          model: c.value,
          live,
          change,
          as_of,
          history:
            live != null
              ? [
                  { date: report.built_on, value: c.value },
                  { date: as_of, value: live },
                ]
              : [],
        },
        signals: signalsOf(c, k),
        sources: sourcesOf(k, live != null ? value(live, unit) : null),
        impact: (c.impact ?? []).map((i) => ({ output: i.output, label: labels.get(i.output) ?? i.output, delta: i.delta })),
      },
    ];
  });
  // stale first, then what's still being checked, then whatever moves an output the most
  const size = (e: TimelineEvent) => Math.max(0, ...e.impact.map((i) => Math.abs(i.delta)));
  const rank = (e: TimelineEvent) => (e.status === "stale" ? 2 : e.status === "checking" ? 1 : 0);
  return events.sort((a, b) => rank(b) - rank(a) || size(b) - size(a));
}

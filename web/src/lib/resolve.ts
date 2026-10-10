/** Whether a stale assumption is still stale, judged from what the cell holds now. */

import type { TimelineEvent } from "../data/timeline";
import { value } from "./format";
import { numberAt, rawRef, type Book } from "./workbook";

export type Outcome =
  | { status: "stale"; note?: string } // note: edited, but still off
  | { status: "updated"; now: number }
  | { status: "gone"; note: string };

/** Within half a percent of today's value counts as updated. */
const close = (a: number, b: number) => (b === 0 ? Math.abs(a) < 1e-9 : Math.abs(a - b) / Math.abs(b) <= 0.005);

// numbers written into a formula, not the digits of cell references like C17 or $B$29
const literals = (formula: string) => [...formula.matchAll(/(?<![\w.$])\d+(?:\.\d+)?(?![\w.])/g)].map((m) => Number(m[0]));

export function assess(book: Book, e: TimelineEvent): Outcome {
  const s = e.state;
  const cell = e.cells[0];
  if (!s || s.live == null || !cell) return { status: "stale" };
  const raw = rawRef(book, cell);
  if (raw === "") return { status: "gone", note: `${cell} was cleared` };

  if (raw.startsWith("=")) {
    const nums = literals(raw);
    if (nums.some((n) => close(n, s.live!))) return { status: "updated", now: s.live };
    if (nums.includes(s.model)) return { status: "stale" };
    return { status: "gone", note: `${cell} no longer uses ${value(s.model, s.unit)}` };
  }

  const now = numberAt(book.hf, cell);
  if (now == null) return { status: "gone", note: `${cell} no longer holds a number` };
  if (close(now, s.live)) return { status: "updated", now };
  if (now === s.model) return { status: "stale" };
  return { status: "stale", note: `Set to ${value(now, s.unit)}; today it's ${value(s.live, s.unit)}` };
}

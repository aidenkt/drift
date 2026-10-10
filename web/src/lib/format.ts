/** Number formats used outside the grid. Finance conventions: signs explicit, units in labels. */

export const MINUS = "−";

export function value(v: number, unit: string): string {
  if (unit === "%") return `${(v * 100).toFixed(2)}%`;
  if (unit === "USD per EUR") return v.toFixed(4);
  if (unit === "$/bbl") return `$${v.toFixed(2)}`;
  if (unit === "$/FEU") return `$${v.toLocaleString("en-US")}`;
  if (Math.abs(v) >= 1000) return v.toLocaleString("en-US", { maximumFractionDigits: 0 });
  return String(v);
}

/** In US$ millions: -12 -> "−$12.0M", 0 -> "$0.0M" */
export function deltaMoney(m: number): string {
  const sign = m < 0 ? MINUS : m > 0 ? "+" : "";
  return `${sign}$${Math.abs(m).toFixed(1)}M`;
}

export function shortDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

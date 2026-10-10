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

/** In US$ millions: 905.48 -> "$905.5M" */
export function money(m: number): string {
  return `${m < 0 ? MINUS : ""}$${Math.abs(m).toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}M`;
}

/** "Today", "Yesterday", "2 days ago", "3 weeks ago" from an ISO date. */
export function ago(iso: string, now = new Date()): string {
  const day = 86_400_000;
  const start = (d: Date) => Date.UTC(d.getFullYear(), d.getMonth(), d.getDate());
  const days = Math.round((start(now) - start(new Date(`${iso.slice(0, 10)}T00:00:00`))) / day);
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 14) return `${days} days ago`;
  if (days < 60) return `${Math.round(days / 7)} weeks ago`;
  return `${Math.round(days / 30)} months ago`;
}

export function clock(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

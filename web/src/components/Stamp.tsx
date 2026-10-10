import type { Check } from "../types";

export default function Stamp({ status }: { status: Check["status"] }) {
  return <span className={`stamp stamp-${status}`}>{status === "stale" ? "STALE" : status}</span>;
}

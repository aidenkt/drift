import type { Check } from "../types";

export default function Stamp({ status }: { status: Check["status"] }) {
  if (status !== "stale") return null;
  return <span style={{ fontFamily: "var(--serif)", color: "var(--accent)" }}>STALE</span>;
}

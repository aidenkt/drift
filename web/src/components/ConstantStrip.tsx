import type { CSSProperties } from "react";
import type { Constant } from "../types";

const RATE_DRIVERS = new Set(["sofr", "ust10y", "fed_funds", "cpi"]);
const PP_DRIVERS = new Set(["tariff", "tax"]);
const LABEL = { stale: "Stale", current: "Current", unknown: "Unknown" } as const;

/** Hover card for a checked constant. Numbers, refs and sources only: no prose. */
export default function ConstantStrip({ constant: c, style }: { constant: Constant; style?: CSSProperties }) {
  const k = c.check;
  const rate = c.driver ? RATE_DRIVERS.has(c.driver) : false;
  const status = k?.status ?? "unchecked";

  return (
    <div className={`cell-tip ${status}`} role="tooltip" style={style}>
      <div className="tip-head">
        <span className="tip-label">{c.label}</span>
        <span className={`tl-badge ${status}`}>{k ? LABEL[k.status] : "Not checked"}</span>
      </div>

      <div className="tip-values mono">
        <span>
          <span className="input">{c.value}</span>
          {k?.live != null && (
            <>
              <span className="tl-arrow"> → </span>
              {k.live}
            </>
          )}
        </span>
        {k?.live != null && (
          <span className={`tl-change ${status}`}>
            {rate
              ? bps(k.live - c.value)
              : c.driver && PP_DRIVERS.has(c.driver)
                ? signed((k.live - c.value) * 100, " pp")
                : k.drift_pct != null
                  ? signed(k.drift_pct, "%")
                  : ""}
          </span>
        )}
      </div>

      {(k?.source_url || k?.as_of || c.feeds > 0) && (
        <div className="tip-foot mono">
          {k?.source_url && <span>{k.source_name ?? new URL(k.source_url).hostname}</span>}
          {k?.as_of && <span>{k.as_of}</span>}
          {c.feeds > 0 && <span>feeds {c.feeds}</span>}
        </div>
      )}
    </div>
  );
}

const signed = (n: number, unit: string) => `${n > 0 ? "+" : n < 0 ? "−" : ""}${Math.abs(n).toFixed(1)}${unit}`;
const bps = (d: number) => signed(d * 10000, " bps").replace(".0 bps", " bps");

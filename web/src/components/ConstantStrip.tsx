import type { Constant } from "../types";
import Stamp from "./Stamp";

const RATE_DRIVERS = new Set(["sofr", "ust10y", "fed_funds", "cpi"]);
const PP_DRIVERS = new Set(["tariff", "tax"]);

/** Data about the selected constant. Numbers, refs and sources only: no prose. */
export default function ConstantStrip({ constant: c }: { constant: Constant }) {
  const k = c.check;
  const rate = c.driver ? RATE_DRIVERS.has(c.driver) : false;

  return (
    <div className={`strip ${k?.status ?? "unchecked"}`}>
      <span className="strip-status">{k ? <Stamp status={k.status} /> : <span className="muted">not checked</span>}</span>
      <span className="strip-label">{c.label}</span>

      <span className="strip-values mono">
        <span className="input">{c.value}</span>
        {k?.live != null && (
          <>
            <span className="muted"> → </span>
            {k.live}
            <span className="strip-drift">
              {rate
                ? bps(k.live - c.value)
                : c.driver && PP_DRIVERS.has(c.driver)
                  ? signed((k.live - c.value) * 100, " pp")
                  : k.drift_pct != null
                    ? signed(k.drift_pct, "%")
                    : ""}
            </span>
          </>
        )}
        {k?.p_stale != null && <span className="strip-drift">p {k.p_stale.toFixed(2)}</span>}
      </span>

      {k?.source_url && (
        <a className="strip-source mono" href={k.source_url} target="_blank" rel="noreferrer">
          {k.source_name ?? new URL(k.source_url).hostname}
        </a>
      )}
      {k?.as_of && <span className="strip-date mono muted">{k.as_of}</span>}
      {c.feeds > 0 && <span className="strip-feeds mono muted">feeds {c.feeds}</span>}
    </div>
  );
}

const signed = (n: number, unit: string) => `${n > 0 ? "+" : n < 0 ? "−" : ""}${Math.abs(n).toFixed(1)}${unit}`;
const bps = (d: number) => signed(d * 10000, " bps").replace(".0 bps", " bps");

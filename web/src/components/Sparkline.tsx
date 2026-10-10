type Props = { points: { date: string; value: number }[]; model: number; stale: boolean; width?: number; height?: number };

/** Value since the model was built, with the model's value as a dashed line. */
export default function Sparkline({ points, model, stale, width = 320, height = 72 }: Props) {
  if (points.length < 2) return null;
  const pad = 6;
  const values = [...points.map((p) => p.value), model];
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const span = hi - lo || 1;
  const x = (i: number) => pad + (i / (points.length - 1)) * (width - pad * 2);
  const y = (v: number) => height - pad - ((v - lo) / span) * (height - pad * 2);
  const path = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(" ");
  const last = points[points.length - 1];

  return (
    <svg className="sparkline" width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img"
      aria-label={`From ${points[0].value} on ${points[0].date} to ${last.value} on ${last.date}; model value ${model}`}>
      <line x1={pad} x2={width - pad} y1={y(model)} y2={y(model)} className="spark-model" />
      <path d={path} className="spark-line" />
      <circle cx={x(points.length - 1)} cy={y(last.value)} r={3.5} className={stale ? "spark-dot stale" : "spark-dot"} />
    </svg>
  );
}

import { fraction, histogramBars, linearScale, niceTicks, signedExtent } from "../lib/charts";
import { formatNumber, formatPercent } from "../lib/format";
import type { Prediction, Task } from "../lib/types";

export function BarList({ items, max, format = (v) => formatNumber(v), label }: {
  items: { label: string; value: number; note?: string }[]; max?: number; format?: (v: number) => string; label: string;
}) {
  const top = max ?? Math.max(1e-12, ...items.map((i) => Math.abs(i.value)));
  return (
    <ul className="barlist" aria-label={label}>
      {items.map((i) => (
        <li key={i.label}>
          <span className="bar-label">{i.label}</span>
          <span className="bar-track"><span className="bar-fill" style={{ width: `${Math.max(0, i.value) / top * 100}%` }} /></span>
          <span className="bar-value">{format(i.value)}{i.note ? <em> {i.note}</em> : null}</span>
        </li>
      ))}
    </ul>
  );
}

export function Histogram({ edges, counts, threshold, label, xFormat = (v) => formatNumber(v, 2) }: {
  edges: number[]; counts: number[]; threshold?: number; label: string; xFormat?: (v: number) => string;
}) {
  const W = 560, H = 180, M = { l: 36, r: 8, t: 8, b: 24 };
  if (!counts.length) return null;
  const bars = histogramBars(edges, counts);
  const x = linearScale([edges[0], edges[edges.length - 1]], [M.l, W - M.r]);
  const ymax = Math.max(...counts, 1);
  const y = linearScale([0, ymax], [H - M.b, M.t]);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label} className="chart">
      {niceTicks(0, ymax, 3).map((t) => (
        <g key={t}><line x1={M.l} x2={W - M.r} y1={y(t)} y2={y(t)} className="grid" /><text x={M.l - 4} y={y(t) + 4} textAnchor="end">{t}</text></g>
      ))}
      {bars.map((b, i) => <rect key={i} x={x(b.x0) + 0.5} y={y(b.count)} width={Math.max(0, x(b.x1) - x(b.x0) - 1)} height={H - M.b - y(b.count)} className="bar-rect" />)}
      {threshold !== undefined && (
        <g><line x1={x(threshold)} x2={x(threshold)} y1={M.t} y2={H - M.b} className="threshold" /><text x={x(threshold) + 4} y={M.t + 10}>flag threshold</text></g>
      )}
      <text x={M.l} y={H - 6}>{xFormat(edges[0])}</text>
      <text x={W - M.r} y={H - 6} textAnchor="end">{xFormat(edges[edges.length - 1])}</text>
    </svg>
  );
}

export function SignedBars({ items, label }: { items: { label: string; value: number; err?: number; note?: string }[]; label: string }) {
  const W = 560, rowH = 26, M = { l: 150, r: 70, t: 6 };
  const ext = signedExtent(items.map((i) => ({ value: i.value, err: i.err })));
  const x = linearScale([-ext, ext], [M.l, W - M.r]);
  const H = M.t + items.length * rowH + 4;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label} className="chart">
      <line x1={x(0)} x2={x(0)} y1={0} y2={H} className="axis" />
      {items.map((it, i) => {
        const cy = M.t + i * rowH + rowH / 2;
        const x0 = x(0), x1 = x(it.value);
        return (
          <g key={it.label}>
            <text x={M.l - 8} y={cy + 4} textAnchor="end">{it.label}</text>
            <rect x={Math.min(x0, x1)} y={cy - 7} width={Math.abs(x1 - x0)} height={14} className={it.value >= 0 ? "pos" : "neg"} />
            {it.err ? <line x1={x(it.value - it.err)} x2={x(it.value + it.err)} y1={cy} y2={cy} className="whisker" /> : null}
            <text x={W - M.r + 6} y={cy + 4}>{it.value >= 0 ? "+" : ""}{formatNumber(it.value, 3)}</text>
          </g>
        );
      })}
    </svg>
  );
}

export function ConfusionMatrix({ labels, matrix }: { labels: string[]; matrix: number[][] }) {
  const rowTotals = matrix.map((r) => r.reduce((a, b) => a + b, 0));
  return (
    <div className="table-wrap" role="region" aria-label="Confusion matrix" tabIndex={0}>
      <table className="confusion">
        <caption className="sr-only">Rows are true classes, columns are predicted classes</caption>
        <thead><tr><th scope="col">True \ predicted</th>{labels.map((l) => <th key={l} scope="col">{l}</th>)}</tr></thead>
        <tbody>
          {matrix.map((row, i) => (
            <tr key={labels[i]}>
              <th scope="row">{labels[i]}</th>
              {row.map((v, j) => {
                const share = rowTotals[i] ? v / rowTotals[i] : 0;
                return <td key={j} className={i === j ? "diag" : ""} style={{ background: `rgba(36,56,214,${(0.08 + share * 0.5).toFixed(2)})` }}>{v}<small> {formatPercent(share)}</small></td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ResidualScatter({ points }: { points: { predicted: number; residual: number }[] }) {
  const W = 560, H = 220, M = { l: 48, r: 8, t: 8, b: 26 };
  if (!points.length) return null;
  const xs = points.map((p) => p.predicted), ys = points.map((p) => p.residual);
  const x = linearScale([Math.min(...xs), Math.max(...xs)], [M.l, W - M.r]);
  const ext = Math.max(1e-9, ...ys.map(Math.abs));
  const y = linearScale([-ext, ext], [H - M.b, M.t]);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Residuals against predicted values" className="chart">
      <line x1={M.l} x2={W - M.r} y1={y(0)} y2={y(0)} className="axis" />
      {points.map((p, i) => <circle key={i} cx={x(p.predicted)} cy={y(p.residual)} r={2.5} className="dot" />)}
      <text x={M.l - 4} y={M.t + 8} textAnchor="end">{formatNumber(ext, 1)}</text>
      <text x={M.l - 4} y={H - M.b} textAnchor="end">{formatNumber(-ext, 1)}</text>
      <text x={W - M.r} y={H - 6} textAnchor="end">predicted value</text>
    </svg>
  );
}

/** The signature element: every prediction is shown with its uncertainty, never as a bare number. */
export function UncertaintyStrip({ task, prediction, target, intervalLevel }: { task: Task; prediction: Prediction; target: string; intervalLevel?: number }) {
  if (task !== "regression" && prediction.probabilities) {
    const entries = Object.entries(prediction.probabilities).sort((a, b) => b[1] - a[1]);
    return (
      <figure className="strip" aria-label={`Predicted ${target}: ${prediction.prediction}`}>
        <figcaption>
          <strong>{String(prediction.prediction)}</strong> at {formatPercent(prediction.confidence, 0)} estimated probability
          {prediction.low_confidence && <span className="badge warn">Low confidence</span>}
        </figcaption>
        <div className="strip-bar" role="img" aria-label={entries.map(([k, v]) => `${k} ${formatPercent(v)}`).join(", ")}>
          {entries.map(([k, v], i) => <span key={k} className={i === 0 ? "seg lead" : "seg"} style={{ flexGrow: Math.max(v, 0.002) }} title={`${k}: ${formatPercent(v, 1)}`}>{v >= 0.12 ? `${k} ${formatPercent(v)}` : ""}</span>)}
        </div>
      </figure>
    );
  }
  const value = Number(prediction.prediction);
  const lo = prediction.interval_low, hi = prediction.interval_high;
  if (lo === undefined || hi === undefined) return <p><strong>{formatNumber(value, 2)}</strong> (no interval available)</p>;
  const pad = (hi - lo) * 0.25 || 1;
  const x = (v: number) => fraction(v, lo - pad, hi + pad) * 100;
  return (
    <figure className="strip" aria-label={`Predicted ${target}: ${formatNumber(value, 2)}, range ${formatNumber(lo, 2)} to ${formatNumber(hi, 2)}`}>
      <figcaption>
        <strong>{formatNumber(value, 2)}</strong> expected, plausible range {formatNumber(lo, 2)} to {formatNumber(hi, 2)}
        {intervalLevel ? <span className="muted"> (aims for about {Math.round(intervalLevel * 100)}% coverage)</span> : null}
      </figcaption>
      <div className="interval" role="img" aria-label="Prediction interval">
        <span className="interval-range" style={{ left: `${x(lo)}%`, width: `${x(hi) - x(lo)}%` }} />
        <span className="interval-point" style={{ left: `${x(value)}%` }} />
      </div>
    </figure>
  );
}

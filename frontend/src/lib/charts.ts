export interface Scale {
  (v: number): number;
  domain: [number, number];
  range: [number, number];
}

export function linearScale(domain: [number, number], range: [number, number]): Scale {
  const [d0, d1] = domain;
  const [r0, r1] = range;
  const span = d1 - d0;
  const fn = ((v: number) => (span === 0 ? (r0 + r1) / 2 : r0 + ((v - d0) / span) * (r1 - r0))) as Scale;
  fn.domain = domain;
  fn.range = range;
  return fn;
}

/** "Nice" tick values covering [min, max] (1-2-5 steps). */
export function niceTicks(min: number, max: number, count = 5): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [];
  if (min === max) return [min];
  const raw = (max - min) / Math.max(count, 1);
  const mag = 10 ** Math.floor(Math.log10(raw));
  const norm = raw / mag;
  const step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10) * mag;
  const start = Math.floor(min / step) * step;
  const ticks: number[] = [];
  for (let t = start; t <= max + step * 0.5; t += step) ticks.push(Number(t.toPrecision(12)));
  return ticks;
}

/** Symmetric extent for signed bars (e.g. contributions) including error whiskers. */
export function signedExtent(items: { value: number; err?: number }[]): number {
  const m = Math.max(0, ...items.map((i) => Math.abs(i.value) + (i.err ?? 0)));
  return m === 0 ? 1 : m;
}

export function histogramBars(edges: number[], counts: number[]): { x0: number; x1: number; count: number }[] {
  return counts.map((count, i) => ({ x0: edges[i], x1: edges[i + 1], count }));
}

/** Position a value within [low, high] as a 0..1 fraction (clamped). */
export function fraction(value: number, low: number, high: number): number {
  if (high === low) return 0.5;
  return Math.min(1, Math.max(0, (value - low) / (high - low)));
}

export function formatNumber(v: number | null | undefined, digits = 3): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "n/a";
  if (!Number.isFinite(v)) return v > 0 ? "inf" : "-inf";
  const abs = Math.abs(v);
  if (abs !== 0 && (abs >= 1e6 || abs < 1e-3)) return v.toExponential(2);
  return Number(v.toFixed(digits)).toLocaleString("en-US", { maximumFractionDigits: digits });
}

export function formatPercent(fraction: number | null | undefined, digits = 0): string {
  return fraction === null || fraction === undefined ? "n/a" : `${(fraction * 100).toFixed(digits)}%`;
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "n/a";
  const d = new Date(iso.endsWith("Z") || /[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`);
  return Number.isNaN(d.getTime()) ? "n/a" : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function truncate(s: string, max = 40): string {
  return s.length <= max ? s : `${s.slice(0, max - 1)}…`;
}

export function humanize(name: string): string {
  const s = name.replace(/_/g, " ").trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** Neutralise spreadsheet formula injection in exported text cells. */
export function sanitizeCell(value: unknown): string {
  const s = value === null || value === undefined ? "" : String(value);
  return /^[=+\-@\t\r]/.test(s) && Number.isNaN(Number(s)) ? `'${s}` : s;
}

export function toCsv(headers: string[], rows: unknown[][]): string {
  const esc = (v: unknown) => {
    const s = sanitizeCell(v);
    return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return [headers.map(esc).join(","), ...rows.map((r) => r.map(esc).join(","))].join("\n") + "\n";
}

export function describeLevel(level: string): string {
  const names: Record<string, string> = { stable: "Stable", moderate: "Moderate shift", significant: "Significant shift", insufficient_data: "Not enough data" };
  return names[level] ?? level;
}

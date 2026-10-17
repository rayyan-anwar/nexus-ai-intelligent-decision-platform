import { useId, type ReactNode } from "react";
import { formatNumber } from "../lib/format";

export function Panel({ title, note, actions, children }: { title: string; note?: string; actions?: ReactNode; children: ReactNode }) {
  const id = useId();
  return (
    <section className="panel" aria-labelledby={id}>
      <header className="panel-head">
        <div>
          <h2 id={id}>{title}</h2>
          {note && <p className="muted">{note}</p>}
        </div>
        {actions && <div className="actions">{actions}</div>}
      </header>
      {children}
    </section>
  );
}

export function PageTitle({ title, lead }: { title: string; lead: string }) {
  return (
    <div className="page-title">
      <h1>{title}</h1>
      <p className="lead">{lead}</p>
    </div>
  );
}

type Variant = "primary" | "quiet" | "danger";
export function Button({
  variant = "quiet", busy, children, ...rest
}: { variant?: Variant; busy?: boolean; children: ReactNode } & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button {...rest} className={`btn ${variant}`} disabled={rest.disabled || busy} aria-busy={busy || undefined}>
      {busy ? "Working…" : children}
    </button>
  );
}

export function Notice({ tone = "info", title, children }: { tone?: "info" | "warn" | "error" | "ok"; title?: string; children?: ReactNode }) {
  return (
    <div className={`notice ${tone}`} role={tone === "error" ? "alert" : "status"}>
      {title && <strong>{title}</strong>}
      {children && <div>{children}</div>}
    </div>
  );
}

export function ErrorNotice({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  const id = (error as { requestId?: string | null }).requestId;
  return (
    <Notice tone="error" title="Something went wrong">
      <p>{error.message}</p>
      {id && <p className="muted">Request id: {id}</p>}
      {onRetry && <Button onClick={onRetry}>Try again</Button>}
    </Notice>
  );
}

export function Loading({ label = "Loading" }: { label?: string }) {
  return <p className="loading" role="status">{label}…</p>;
}

export function Empty({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="empty">
      <strong>{title}</strong>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: (id: string) => ReactNode }) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {children(id)}
      {hint && <small className="muted">{hint}</small>}
    </div>
  );
}

export function Badge({ tone = "neutral", children }: { tone?: "neutral" | "ok" | "warn" | "bad" | "accent"; children: ReactNode }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

export function ProgressBar({ value, label }: { value: number; label: string }) {
  const pct = Math.round(Math.min(1, Math.max(0, value)) * 100);
  return (
    <div className="progress" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
      <div style={{ width: `${pct}%` }} />
    </div>
  );
}

export function DataTable({ columns, rows, caption }: { columns: string[]; rows: ReactNode[][]; caption?: string }) {
  return (
    <div className="table-wrap" tabIndex={0} role="region" aria-label={caption ?? "Data table"}>
      <table>
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead><tr>{columns.map((c) => <th key={c} scope="col">{c}</th>)}</tr></thead>
        <tbody>
          {rows.map((r, i) => <tr key={i}>{r.map((cell, j) => <td key={j}>{cell}</td>)}</tr>)}
        </tbody>
      </table>
    </div>
  );
}

export function MetricList({ metrics, keys }: { metrics: Record<string, number | null | undefined>; keys: string[] }) {
  return (
    <dl className="metrics">
      {keys.filter((k) => k in metrics).map((k) => (
        <div key={k}><dt>{k.replace(/_/g, " ")}</dt><dd>{formatNumber(metrics[k])}</dd></div>
      ))}
    </dl>
  );
}

export function Warnings({ items, tone = "warn", title }: { items: string[]; tone?: "warn" | "info"; title: string }) {
  if (!items.length) return null;
  return (
    <Notice tone={tone} title={title}>
      <ul>{items.map((w) => <li key={w}>{w}</li>)}</ul>
    </Notice>
  );
}

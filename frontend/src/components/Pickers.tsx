import { useEffect, useRef, useState } from "react";
import { useApp } from "../state";
import { useAsync } from "../lib/useAsync";
import type { Dataset, FeatureSpec, ModelSummary } from "../lib/types";
import { formatNumber } from "../lib/format";
import { Button, ErrorNotice, Field, Notice } from "./ui";

/** Upload a CSV or load the bundled synthetic sample. Calls onCreated with the new dataset. */
export function DatasetActions({ onCreated }: { onCreated: (d: Dataset) => void }) {
  const { api } = useApp();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState<"upload" | "demo" | null>(null);
  const [error, setError] = useState<Error | null>(null);

  async function run(kind: "upload" | "demo", fn: () => Promise<Dataset>) {
    setBusy(kind);
    setError(null);
    try {
      onCreated(await fn());
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="stack">
      <div className="row">
        <input ref={input} type="file" accept=".csv,text/csv" hidden aria-label="Choose a CSV file"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) void run("upload", () => api.uploadDataset(f)); e.target.value = ""; }} />
        <Button variant="primary" busy={busy === "upload"} onClick={() => input.current?.click()}>Upload CSV</Button>
        <Button busy={busy === "demo"} onClick={() => void run("demo", () => api.createDemoDataset())}>Load synthetic demo data</Button>
      </div>
      {error && <ErrorNotice error={error} />}
    </div>
  );
}

export function DatasetSelect({ label = "Dataset", value, onChange, reloadKey = 0 }: {
  label?: string; value: string | null; onChange: (id: string, ds?: Dataset) => void; reloadKey?: number;
}) {
  const { api } = useApp();
  const list = useAsync(() => api.listDatasets(), [api, reloadKey]);
  const datasets = list.data ?? [];

  useEffect(() => {
    if (list.data && list.data.length && (!value || !list.data.some((d) => d.id === value))) onChange(list.data[0].id, list.data[0]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [list.data]);

  if (list.error) return <ErrorNotice error={list.error} onRetry={list.reload} />;
  if (!list.loading && datasets.length === 0) {
    return (
      <Notice tone="info" title="No datasets yet">
        <p>Upload a CSV file or load the synthetic demo data to begin.</p>
        <DatasetActions onCreated={(d) => { onChange(d.id, d); list.reload(); }} />
      </Notice>
    );
  }
  return (
    <Field label={label}>
      {(id) => (
        <select id={id} value={value ?? ""} onChange={(e) => onChange(e.target.value, datasets.find((d) => d.id === e.target.value))}>
          {datasets.map((d) => <option key={d.id} value={d.id}>{d.name}{d.is_synthetic ? " (synthetic)" : ""} - {d.n_rows.toLocaleString()} rows</option>)}
        </select>
      )}
    </Field>
  );
}

export function ModelSelect({ value, onChange, reloadKey = 0, onLoaded }: {
  value: string | null; onChange: (id: string) => void; reloadKey?: number; onLoaded?: (models: ModelSummary[]) => void;
}) {
  const { api, navigate } = useApp();
  const list = useAsync(() => api.listModels(), [api, reloadKey]);
  const models = list.data ?? [];

  useEffect(() => {
    if (!list.data) return;
    onLoaded?.(list.data);
    if (list.data.length && (!value || !list.data.some((m) => m.id === value))) onChange(list.data[0].id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [list.data]);

  if (list.error) return <ErrorNotice error={list.error} onRetry={list.reload} />;
  if (!list.loading && models.length === 0) {
    return (
      <Notice tone="info" title="No trained models yet">
        <p>Train a model first, then come back here.</p>
        <Button variant="primary" onClick={() => navigate("training")}>Go to model training</Button>
      </Notice>
    );
  }
  return (
    <Field label="Model">
      {(id) => (
        <select id={id} value={value ?? ""} onChange={(e) => onChange(e.target.value)}>
          {models.map((m) => <option key={m.id} value={m.id}>{m.name} - predicts {m.target} ({m.task})</option>)}
        </select>
      )}
    </Field>
  );
}

/** Form generated from the model's input schema. */
export function RecordForm({ features, onSubmit, busy, submitLabel }: {
  features: FeatureSpec[]; onSubmit: (record: Record<string, unknown>) => void; busy?: boolean; submitLabel: string;
}) {
  const initial = () => Object.fromEntries(features.map((f) => [f.name, f.kind === "numeric" ? (f.median === null ? "" : String(f.median)) : (f.mode ?? "")]));
  const [values, setValues] = useState<Record<string, string>>(initial);
  const [touched, setTouched] = useState(false);

  const invalid = (f: FeatureSpec) => f.kind === "numeric" && values[f.name] !== "" && Number.isNaN(Number(values[f.name]));
  const hasErrors = features.some(invalid);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (hasErrors) return;
    onSubmit(Object.fromEntries(features.map((f) => {
      const v = values[f.name];
      return [f.name, v === "" ? null : f.kind === "numeric" ? Number(v) : v];
    })));
  }

  return (
    <form onSubmit={submit} noValidate className="stack">
      <div className="form-grid">
        {features.map((f) => (
          <Field key={f.name} label={f.name.replace(/_/g, " ")}
            hint={f.kind === "numeric" ? `Training range ${formatNumber(f.min, 2)} to ${formatNumber(f.max, 2)}` : "Leave blank if unknown"}>
            {(id) => f.kind === "numeric" ? (
              <input id={id} inputMode="decimal" value={values[f.name]} aria-invalid={touched && invalid(f) || undefined}
                aria-describedby={touched && invalid(f) ? `${id}-err` : undefined}
                onChange={(e) => setValues({ ...values, [f.name]: e.target.value })} />
            ) : (
              <select id={id} value={values[f.name]} onChange={(e) => setValues({ ...values, [f.name]: e.target.value })}>
                <option value="">(missing)</option>
                {(f.categories ?? []).map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            )}
          </Field>
        ))}
      </div>
      {touched && hasErrors && <Notice tone="error" title="Fix the highlighted fields">Numeric fields must contain a number or be empty.</Notice>}
      <div><Button type="submit" variant="primary" busy={busy}>{submitLabel}</Button></div>
    </form>
  );
}

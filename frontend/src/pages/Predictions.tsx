import { useRef, useState } from "react";
import { useApp } from "../state";
import { useAsync, download } from "../lib/useAsync";
import type { PredictResponse } from "../lib/types";
import { toCsv } from "../lib/format";
import { Button, ErrorNotice, Loading, Notice, PageTitle, Panel, Warnings } from "../components/ui";
import { ModelSelect, RecordForm } from "../components/Pickers";
import { UncertaintyStrip } from "../components/charts";

export default function Predictions() {
  const { api, selection, select } = useApp();
  const modelId = selection.modelId;
  const model = useAsync(() => (modelId ? api.getModel(modelId) : Promise.resolve(undefined)), [api, modelId]);
  const [result, setResult] = useState<{ response: PredictResponse; record: Record<string, unknown> } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [batchBusy, setBatchBusy] = useState(false);
  const file = useRef<HTMLInputElement>(null);
  const m = model.data;

  async function predict(record: Record<string, unknown>) {
    if (!modelId) return;
    setBusy(true); setError(null);
    try { setResult({ response: await api.predict(modelId, [record]), record }); } catch (e) { setError(e as Error); setResult(null); } finally { setBusy(false); }
  }

  async function batch(f: File) {
    if (!modelId) return;
    setBatchBusy(true); setError(null);
    try { download("nexus-predictions.csv", await api.predictCsv(modelId, f)); } catch (e) { setError(e as Error); } finally { setBatchBusy(false); }
  }

  function exportOne() {
    if (!result) return;
    const p = result.response.predictions[0];
    const keys = Object.keys(result.record);
    const extra = Object.keys(p).filter((k) => k !== "probabilities");
    download("nexus-prediction.csv", toCsv([...keys, ...extra], [[...keys.map((k) => result.record[k]), ...extra.map((k) => (p as unknown as Record<string, unknown>)[k])]]));
  }

  const p = result?.response.predictions[0];

  return (
    <>
      <PageTitle title="Predictions" lead="Enter a record to get a prediction with its uncertainty, or score a whole CSV file." />
      <Panel title="Model"><ModelSelect value={modelId} onChange={(id) => { select({ modelId: id }); setResult(null); }} /></Panel>
      {model.loading && modelId && <Loading label="Loading model" />}
      {model.error && <ErrorNotice error={model.error} onRetry={model.reload} />}
      {m && (
        <>
          <Panel title="Single record" note={`Predicts ${m.target}. Fields start at typical training values; change what you know.`}>
            <RecordForm key={m.id} features={m.schema.features} busy={busy} submitLabel="Predict" onSubmit={(r) => void predict(r)} />
          </Panel>
          {error && <ErrorNotice error={error} />}
          {result && p && (
            <Panel title="Prediction" actions={<Button onClick={exportOne}>Download as CSV</Button>}>
              <div className="stack">
                <UncertaintyStrip task={m.task} prediction={p} target={m.target} intervalLevel={m.interval?.level} />
                <Warnings title="Input problems" items={result.response.issues} />
                <Notice tone="info" title="How to read this">{result.response.uncertainty_note}</Notice>
              </div>
            </Panel>
          )}
          <Panel title="Whole file" note="Upload a CSV with the same columns. You get the file back with prediction columns added.">
            <input ref={file} type="file" accept=".csv,text/csv" hidden aria-label="Choose a CSV file to score"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) void batch(f); e.target.value = ""; }} />
            <Button busy={batchBusy} onClick={() => file.current?.click()}>Score a CSV file</Button>
          </Panel>
        </>
      )}
    </>
  );
}

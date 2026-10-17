import { useEffect, useState } from "react";
import { useApp } from "../state";
import { useAsync } from "../lib/useAsync";
import type { Experiment, ExperimentSummary, Task } from "../lib/types";
import { formatNumber } from "../lib/format";
import { Badge, Button, ErrorNotice, Field, Loading, Notice, PageTitle, Panel, ProgressBar, Warnings } from "../components/ui";
import { DatasetSelect } from "../components/Pickers";

const TERMINAL = new Set(["succeeded", "failed"]);

export default function Training() {
  const { api, selection, select, navigate } = useApp();
  const datasetId = selection.datasetId;
  const profile = useAsync(() => (datasetId ? api.profile(datasetId) : Promise.resolve(undefined)), [api, datasetId]);

  const [target, setTarget] = useState("");
  const [task, setTask] = useState<"" | Task>("");
  const [seed, setSeed] = useState("42");
  const [testSize, setTestSize] = useState("0.2");
  const [valSize, setValSize] = useState("0.2");
  const [excluded, setExcluded] = useState<string[]>([]);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [run, setRun] = useState<Experiment | null>(null);
  const [summary, setSummary] = useState<ExperimentSummary | null>(null);

  const columns = profile.data?.profile.columns ?? [];
  const suggestions = profile.data?.target_suggestions ?? [];

  useEffect(() => { setTarget(""); setExcluded([]); setRun(null); setSummary(null); }, [datasetId]);

  // Poll the background job until it finishes.
  useEffect(() => {
    if (!run || TERMINAL.has(run.status)) return;
    const timer = setInterval(async () => {
      try {
        const next = await api.getExperiment(run.id);
        setRun(next);
        if (next.status === "succeeded") { select({ experimentId: next.id, modelId: next.model_id }); setSummary(await api.metrics(next.id)); }
      } catch (e) {
        setError(e as Error);
        clearInterval(timer);
      }
    }, 1000);
    return () => clearInterval(timer);
  }, [run, api, select]);

  async function start() {
    if (!datasetId || !target) return;
    setStarting(true); setError(null); setSummary(null);
    try {
      setRun(await api.startExperiment({
        dataset_id: datasetId, target, task: task || null, seed: Number(seed), test_size: Number(testSize), val_size: Number(valSize),
        exclude_columns: excluded.filter((c) => c !== target),
      }));
    } catch (e) {
      setError(e as Error);
    } finally {
      setStarting(false);
    }
  }

  const otherTargets = suggestions.map((s) => s.column).filter((c) => c !== target);
  const running = run !== null && !TERMINAL.has(run.status);

  return (
    <>
      <PageTitle title="Model training" lead="Choose what to predict. Models are compared on a validation split; the held-out test split is used once, after the choice is made." />
      <Panel title="1. Dataset"><DatasetSelect value={datasetId} onChange={(d) => select({ datasetId: d })} /></Panel>
      {profile.loading && datasetId && <Loading label="Reading columns" />}
      {profile.error && <ErrorNotice error={profile.error} onRetry={profile.reload} />}
      {profile.data && (
        <Panel title="2. Confirm the target" note="Suggestions are guesses based on column names and values. You decide what to predict.">
          <div className="stack">
            <div className="row wrap" aria-label="Suggested targets">
              {suggestions.map((s) => (
                <Button key={s.column} variant={target === s.column ? "primary" : "quiet"} aria-pressed={target === s.column} onClick={() => { setTarget(s.column); if (!task) setTask(""); }}>
                  {s.column} <small>({s.task})</small>
                </Button>
              ))}
            </div>
            <Field label="Target column">
              {(id) => (
                <select id={id} value={target} onChange={(e) => setTarget(e.target.value)}>
                  <option value="">Select a column</option>
                  {columns.map((c) => <option key={c.name} value={c.name}>{c.name} ({c.kind.replace("_", " ")})</option>)}
                </select>
              )}
            </Field>
            <Field label="Task type" hint="Leave on automatic unless the detected type is wrong, for example a count that should be regression.">
              {(id) => (
                <select id={id} value={task} onChange={(e) => setTask(e.target.value as "" | Task)}>
                  <option value="">Detect automatically</option>
                  <option value="binary">Binary classification</option>
                  <option value="multiclass">Multiclass classification</option>
                  <option value="regression">Regression</option>
                </select>
              )}
            </Field>
          </div>
        </Panel>
      )}
      {profile.data && target && (
        <Panel title="3. Options" note="Defaults are sensible for most data.">
          <div className="stack">
            {otherTargets.length > 0 && (
              <Notice tone="warn" title="Other outcome columns can leak the answer">
                <p>Columns such as {otherTargets.slice(0, 3).join(", ")} may be derived from or related to the target. Exclude any that would not be known when you make a real prediction.</p>
                <Button onClick={() => setExcluded(Array.from(new Set([...excluded, ...otherTargets])))}>Exclude the other suggested targets</Button>
              </Notice>
            )}
            <fieldset className="checks">
              <legend>Columns to leave out</legend>
              {columns.filter((c) => c.name !== target).map((c) => (
                <label key={c.name}><input type="checkbox" checked={excluded.includes(c.name)}
                  onChange={(e) => setExcluded(e.target.checked ? [...excluded, c.name] : excluded.filter((x) => x !== c.name))} /> {c.name}</label>
              ))}
            </fieldset>
            <div className="form-grid">
              <Field label="Random seed" hint="Same seed, same data: same result.">{(id) => <input id={id} inputMode="numeric" value={seed} onChange={(e) => setSeed(e.target.value)} />}</Field>
              <Field label="Test share">{(id) => <input id={id} inputMode="decimal" value={testSize} onChange={(e) => setTestSize(e.target.value)} />}</Field>
              <Field label="Validation share">{(id) => <input id={id} inputMode="decimal" value={valSize} onChange={(e) => setValSize(e.target.value)} />}</Field>
            </div>
            <div><Button variant="primary" busy={starting || running} onClick={() => void start()}>Train models</Button></div>
          </div>
        </Panel>
      )}
      {error && <ErrorNotice error={error} />}
      {run && (
        <Panel title="Progress">
          <div className="stack">
            <p><Badge tone={run.status === "succeeded" ? "ok" : run.status === "failed" ? "bad" : "accent"}>{run.status}</Badge> {run.stage ?? ""}</p>
            <ProgressBar value={run.progress} label="Training progress" />
            {run.status === "failed" && <Notice tone="error" title="Training did not finish">{run.error_message}</Notice>}
          </div>
        </Panel>
      )}
      {summary && run?.status === "succeeded" && (
        <Panel title="Result" actions={<>
          <Button variant="primary" onClick={() => navigate("predictions")}>Make predictions</Button>
          <Button onClick={() => navigate("comparison")}>Compare experiments</Button>
        </>}>
          <div className="stack">
            <p>
              Selected <strong>{summary.selected_model}</strong> by validation {summary.primary_metric.name.replace("_", " ")}.
              Held-out test {summary.primary_metric.name.replace("_", " ")}: <strong>{formatNumber(summary.test_metrics[summary.primary_metric.name])}</strong>{" "}
              (baseline {formatNumber(summary.baseline.test[summary.primary_metric.name])}).
            </p>
            <Warnings title="Things to know" items={summary.warnings} />
          </div>
        </Panel>
      )}
    </>
  );
}

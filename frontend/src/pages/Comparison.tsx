import { useState } from "react";
import { useApp } from "../state";
import { useAsync } from "../lib/useAsync";
import type { CompareResponse } from "../lib/types";
import { formatDate, formatNumber } from "../lib/format";
import { Badge, Button, DataTable, Empty, ErrorNotice, Loading, MetricList, Notice, PageTitle, Panel, Warnings } from "../components/ui";
import { BarList, ConfusionMatrix, ResidualScatter } from "../components/charts";

const CLS_KEYS = ["accuracy", "precision", "recall", "f1", "f1_macro", "roc_auc", "pr_auc", "brier"];
const REG_KEYS = ["mae", "rmse", "r2", "median_ae"];

export default function Comparison() {
  const { api, navigate } = useApp();
  const experiments = useAsync(() => api.listExperiments(), [api]);
  const done = (experiments.data ?? []).filter((e) => e.status === "succeeded");
  const [checked, setChecked] = useState<string[]>([]);
  const [detailId, setDetailId] = useState<string | null>(null);
  const [cmp, setCmp] = useState<CompareResponse | null>(null);
  const [cmpError, setCmpError] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);
  const detail = useAsync(() => (detailId ? api.metrics(detailId) : Promise.resolve(undefined)), [api, detailId]);
  const d = detail.data;

  async function compare() {
    setBusy(true); setCmpError(null);
    try { setCmp(await api.compare(checked)); } catch (e) { setCmpError(e as Error); setCmp(null); } finally { setBusy(false); }
  }

  const toggle = (id: string, on: boolean) => setChecked(on ? [...checked, id].slice(-6) : checked.filter((x) => x !== id));

  return (
    <>
      <PageTitle title="Experiment comparison" lead="Compare finished experiments side by side. Only experiments with the same target and task are directly comparable." />
      <Panel title="Finished experiments" note="Tick two to six to compare, or open one for details.">
        {experiments.loading ? <Loading /> : experiments.error ? <ErrorNotice error={experiments.error} onRetry={experiments.reload} /> : done.length === 0 ? (
          <Empty title="No finished experiments" action={<Button variant="primary" onClick={() => navigate("training")}>Train a model</Button>}>Train a model to see it here.</Empty>
        ) : (
          <div className="stack">
            <DataTable caption="Finished experiments" columns={["Compare", "Target", "Task", "Finished", ""]}
              rows={done.map((e) => [
                <input key="c" type="checkbox" aria-label={`Compare experiment for ${e.target}`} checked={checked.includes(e.id)} onChange={(ev) => toggle(e.id, ev.target.checked)} />,
                e.target, e.task ?? "n/a", formatDate(e.finished_at),
                <Button key="v" onClick={() => setDetailId(e.id)}>Open details</Button>,
              ])} />
            <div><Button variant="primary" busy={busy} disabled={checked.length < 2} onClick={() => void compare()}>Compare {checked.length >= 2 ? `${checked.length} experiments` : "(select at least 2)"}</Button></div>
          </div>
        )}
      </Panel>
      {cmpError && <ErrorNotice error={cmpError} />}
      {cmp && (
        <Panel title="Side by side">
          {cmp.notes.map((n) => <Notice key={n} tone="warn" title="Not like for like">{n}</Notice>)}
          <DataTable caption="Experiment comparison" columns={["Target", "Selected model", "Selection metric", "Validation", "Test", "Baseline test"]}
            rows={cmp.experiments.map((r) => {
              const m = r.primary_metric.name;
              return [r.target, r.selected_model, `${m.replace("_", " ")} (${r.primary_metric.direction} is better)`, formatNumber(r.validation[m]), formatNumber(r.test[m]), formatNumber(r.baseline_test[m])];
            })} />
          {new Set(cmp.experiments.map((r) => r.primary_metric.name)).size === 1 && (
            <BarList label="Held-out test score" items={cmp.experiments.map((r) => ({ label: `${r.target} (${r.selected_model})`, value: Math.max(0, r.test[r.primary_metric.name] ?? 0) }))} />
          )}
        </Panel>
      )}
      {detail.loading && detailId && <Loading label="Loading results" />}
      {detail.error && <ErrorNotice error={detail.error} onRetry={detail.reload} />}
      {d && (
        <>
          <Panel title={`Models for ${d.target}`} note={`Selected on the validation split by ${d.primary_metric.name.replace("_", " ")}; ${d.split.n_train} train, ${d.split.n_validation} validation, ${d.split.n_test} test rows.`}>
            <DataTable caption="Candidate models" columns={["Model", "Validation", "Fit time", ""]}
              rows={[
                ...d.candidates.map((c) => [c.name, <MetricList key="m" metrics={c.validation} keys={d.task === "regression" ? REG_KEYS : CLS_KEYS} />, `${c.fit_seconds}s`, c.selected ? <Badge key="b" tone="accent">Selected</Badge> : ""]),
                [d.baseline.name, <MetricList key="bm" metrics={d.baseline.validation} keys={d.task === "regression" ? REG_KEYS : CLS_KEYS} />, "", <Badge key="bb">Baseline</Badge>],
              ]} />
          </Panel>
          <Panel title="Held-out test results" note="Evaluated once, after the model was chosen.">
            <MetricList metrics={d.test_metrics} keys={d.task === "regression" ? REG_KEYS : CLS_KEYS} />
            {d.test_metrics.confusion_matrix && <ConfusionMatrix labels={d.test_metrics.confusion_matrix.labels} matrix={d.test_metrics.confusion_matrix.matrix} />}
            {d.test_metrics.residuals && <ResidualScatter points={d.test_metrics.residuals.sample} />}
            {d.interval && <p className="muted">Prediction intervals aim for about {Math.round(d.interval.level * 100)}% coverage (half-width {formatNumber(d.interval.half_width, 2)}), using {d.interval.method}.</p>}
          </Panel>
          <Panel title="Warnings and limitations">
            <Warnings title="Raised during training" items={d.warnings} />
            <ul>{d.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
          </Panel>
        </>
      )}
    </>
  );
}

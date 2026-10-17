import { useApp } from "../state";
import { useAsync } from "../lib/useAsync";
import { formatDate } from "../lib/format";
import { Badge, DataTable, ErrorNotice, Loading, Notice, PageTitle, Panel } from "../components/ui";
import { DatasetActions } from "../components/Pickers";

const STEPS: [string, string, string][] = [
  ["datasets", "Explore a dataset", "Upload a CSV or load the synthetic demo and review each column."],
  ["quality", "Check data quality", "See missing values, duplicates and invalid entries before modelling."],
  ["training", "Train and compare models", "Confirm the target column; models are chosen on a validation split."],
  ["predictions", "Predict for new records", "Every prediction comes with its uncertainty."],
  ["explain", "Understand the model", "Global importance and per-record explanations, with caveats."],
  ["anomalies", "Find unusual records", "Isolation Forest scores with adjustable sensitivity."],
  ["drift", "Watch for drift", "Compare new data with the data you trained on."],
];

export default function Overview() {
  const { api, select, navigate } = useApp();
  const health = useAsync(() => api.health(), [api]);
  const settings = useAsync(() => api.settings(), [api]);
  const datasets = useAsync(() => api.listDatasets(), [api]);
  const models = useAsync(() => api.listModels(), [api]);
  const experiments = useAsync(() => api.listExperiments(), [api]);

  return (
    <>
      <PageTitle title="Overview" lead="Turn a table of data into predictions you can question: each one comes with its uncertainty, an explanation and the checks that apply." />
      {health.error && <ErrorNotice error={health.error} onRetry={health.reload} />}
      <Panel title="System">
        {health.loading || settings.loading ? <Loading /> : (
          <dl className="facts">
            <div><dt>API</dt><dd>{health.data ? <Badge tone={health.data.status === "ok" ? "ok" : "bad"}>{health.data.status === "ok" ? "Running" : "Degraded"}</Badge> : "Unavailable"}</dd></div>
            <div><dt>Version</dt><dd>{health.data?.version ?? "n/a"}</dd></div>
            <div><dt>Datasets</dt><dd>{datasets.data?.length ?? "n/a"}</dd></div>
            <div><dt>Trained models</dt><dd>{models.data?.length ?? "n/a"}</dd></div>
            <div><dt>Data retention</dt><dd>{settings.data ? (settings.data.retention_days ? `${settings.data.retention_days} days` : "Until deleted") : "n/a"}</dd></div>
            <div><dt>Native accelerator</dt><dd>{settings.data ? (settings.data.native_accelerator ? "In use" : "Not built (optional)") : "n/a"}</dd></div>
          </dl>
        )}
      </Panel>
      <Panel title="Start here" note="No data of your own yet? The synthetic sample is made-up data for trying the workflow.">
        <DatasetActions onCreated={(d) => { select({ datasetId: d.id }); navigate("datasets"); }} />
      </Panel>
      <Panel title="Workflow">
        <ol className="steps">
          {STEPS.map(([route, title, text]) => (
            <li key={route}><a href={`#/${route}`}><strong>{title}</strong></a><span className="muted"> {text}</span></li>
          ))}
        </ol>
      </Panel>
      <Panel title="Recent experiments">
        {experiments.loading ? <Loading /> : experiments.error ? <ErrorNotice error={experiments.error} onRetry={experiments.reload} /> : (
          (experiments.data ?? []).length === 0
            ? <p className="muted">None yet. Train a model to see results here.</p>
            : <DataTable caption="Recent experiments" columns={["Target", "Task", "Status", "Started"]}
                rows={(experiments.data ?? []).slice(0, 6).map((e) => [e.target, e.task ?? "n/a", <Badge key="s" tone={e.status === "succeeded" ? "ok" : e.status === "failed" ? "bad" : "accent"}>{e.status}</Badge>, formatDate(e.created_at)])} />
        )}
      </Panel>
      <Notice tone="info" title="How to read results">
        Predictions are probabilistic estimates from patterns in past data. They are not guarantees, and explanations describe the model, not real-world causes.
      </Notice>
    </>
  );
}

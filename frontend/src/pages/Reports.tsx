import { useState } from "react";
import { useApp } from "../state";
import { useAsync, download } from "../lib/useAsync";
import { formatDate } from "../lib/format";
import { Badge, Button, DataTable, Empty, ErrorNotice, Field, Loading, Notice, PageTitle, Panel } from "../components/ui";

export default function Reports() {
  const { api, token, setToken, selection, select } = useApp();
  const experiments = useAsync(() => api.listExperiments(), [api]);
  const models = useAsync(() => api.listModels(), [api]);
  const settings = useAsync(() => api.settings(), [api, token]);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function guard(id: string, fn: () => Promise<void>) {
    setBusyId(id); setError(null); setMessage(null);
    try { await fn(); } catch (e) { setError(e as Error); } finally { setBusyId(null); }
  }

  const openReport = (id: string) => guard(id, async () => {
    const html = await api.reportHtml(id);
    const url = URL.createObjectURL(new Blob([html], { type: "text/html" }));
    window.open(url, "_blank", "noopener");
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  });
  const saveReport = (id: string) => guard(`dl-${id}`, async () => download(`nexus-report-${id}.html`, await api.reportHtml(id), "text/html"));
  const removeModel = (id: string) => {
    if (!window.confirm("Delete this model and its saved file? This cannot be undone.")) return Promise.resolve();
    return guard(`rm-${id}`, async () => {
      await api.deleteModel(id);
      if (selection.modelId === id) select({ modelId: null });
      models.reload();
      setMessage("Model deleted.");
    });
  };
  const purge = () => guard("purge", async () => {
    const r = await api.purgeExpired();
    setMessage(`${r.datasets_deleted} expired dataset(s) deleted.`);
  });

  const done = (experiments.data ?? []).filter((e) => e.status === "succeeded");
  const s = settings.data;

  return (
    <>
      <PageTitle title="Reports and settings" lead="Download a self-contained report for any finished experiment, manage stored models, and review how your data is handled." />
      {error && <ErrorNotice error={error} />}
      {message && <Notice tone="ok" title={message} />}
      <Panel title="Experiment reports" note="Each report lists the models compared, held-out results, warnings and the exact settings needed to reproduce the run.">
        {experiments.loading ? <Loading /> : experiments.error ? <ErrorNotice error={experiments.error} onRetry={experiments.reload} /> : done.length === 0 ? (
          <Empty title="No finished experiments">Train a model to create a report.</Empty>
        ) : (
          <DataTable caption="Reports" columns={["Target", "Task", "Finished", ""]}
            rows={done.map((e) => [e.target, e.task ?? "n/a", formatDate(e.finished_at),
              <span key="a" className="row">
                <Button busy={busyId === e.id} onClick={() => void openReport(e.id)}>View</Button>
                <Button busy={busyId === `dl-${e.id}`} onClick={() => void saveReport(e.id)}>Download HTML</Button>
              </span>])} />
        )}
      </Panel>
      <Panel title="Stored models" note="Deleting a model also removes its saved file. Experiment results stay.">
        {models.loading ? <Loading /> : (models.data ?? []).length === 0 ? <p className="muted">No models stored.</p> : (
          <DataTable caption="Models" columns={["Model", "Predicts", "Task", "Created", ""]}
            rows={(models.data ?? []).map((m) => [m.name, m.target, m.task, formatDate(m.created_at),
              <Button key="d" variant="danger" busy={busyId === `rm-${m.id}`} onClick={() => void removeModel(m.id)}>Delete</Button>])} />
        )}
      </Panel>
      <Panel title="Access" note="Needed only when the server requires a token. It is kept in memory for this tab and never written to storage.">
        <Field label="API token">{(id) => <input id={id} type="password" autoComplete="off" spellCheck={false} value={token} onChange={(e) => setToken(e.target.value)} />}</Field>
      </Panel>
      <Panel title="Server settings">
        {settings.loading ? <Loading /> : settings.error ? <ErrorNotice error={settings.error} onRetry={settings.reload} /> : s && (
          <div className="stack">
            <dl className="facts">
              <div><dt>Environment</dt><dd>{s.environment}</dd></div>
              <div><dt>Token required</dt><dd>{s.auth_required ? <Badge tone="ok">Yes</Badge> : <Badge tone="warn">No (local use)</Badge>}</dd></div>
              <div><dt>Datasets deleted after</dt><dd>{s.retention_days ? `${s.retention_days} days` : "Never automatically"}</dd></div>
              <div><dt>Upload limit</dt><dd>{s.max_upload_mb} MB, {s.max_rows.toLocaleString()} rows, {s.max_cols} columns</dd></div>
              <div><dt>Request limit</dt><dd>{s.rate_limit_per_minute ? `${s.rate_limit_per_minute} per minute` : "None"}</dd></div>
            </dl>
            <div><Button busy={busyId === "purge"} onClick={() => void purge()}>Delete expired datasets now</Button> <small className="muted">Needs an administrator token when tokens are enabled.</small></div>
          </div>
        )}
      </Panel>
      <Notice tone="info" title="Privacy">Uploaded files and model files stay on the server you run. Prediction history stores a fingerprint of each request and summary counts, never the values you entered.</Notice>
    </>
  );
}

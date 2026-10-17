import { useState } from "react";
import { useApp } from "../state";
import { useAsync } from "../lib/useAsync";
import { formatBytes, formatDate, formatNumber } from "../lib/format";
import { Badge, Button, DataTable, Empty, ErrorNotice, Loading, Notice, PageTitle, Panel } from "../components/ui";
import { DatasetActions, DatasetSelect } from "../components/Pickers";
import { Histogram } from "../components/charts";

export default function DatasetExplorer() {
  const { api, selection, select } = useApp();
  const [reload, setReload] = useState(0);
  const id = selection.datasetId;
  const profile = useAsync(() => (id ? api.profile(id) : Promise.resolve(undefined)), [api, id]);
  const preview = useAsync(() => (id ? api.preview(id, 25) : Promise.resolve(undefined)), [api, id]);
  const [chosen, setChosen] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<Error | null>(null);

  const p = profile.data;
  const col = p?.profile.columns.find((c) => c.name === chosen);

  async function remove() {
    if (!id || !window.confirm("Delete this dataset and every experiment and model built from it? This cannot be undone.")) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await api.deleteDataset(id);
      select({ datasetId: null, modelId: null, experimentId: null });
      setReload((r) => r + 1);
    } catch (e) {
      setDeleteError(e as Error);
    } finally {
      setDeleting(false);
    }
  }

  return (
    <>
      <PageTitle title="Dataset explorer" lead="Review every column before you model it. Nothing here changes your data." />
      <Panel title="Choose data" actions={id ? <Button variant="danger" busy={deleting} onClick={() => void remove()}>Delete dataset</Button> : undefined}>
        <div className="stack">
          <DatasetSelect value={id} reloadKey={reload} onChange={(d) => select({ datasetId: d })} />
          <DatasetActions onCreated={(d) => { select({ datasetId: d.id }); setReload((r) => r + 1); }} />
          {deleteError && <ErrorNotice error={deleteError} />}
        </div>
      </Panel>
      {profile.loading && id && <Loading label="Profiling dataset" />}
      {profile.error && <ErrorNotice error={profile.error} onRetry={profile.reload} />}
      {p && (
        <>
          {p.dataset.is_synthetic && <Notice tone="info" title="Synthetic data">This sample was generated for demonstration. It does not describe real people or businesses.</Notice>}
          <Panel title="Summary">
            <dl className="facts">
              <div><dt>Rows</dt><dd>{p.profile.n_rows.toLocaleString()}</dd></div>
              <div><dt>Columns</dt><dd>{p.profile.n_cols}</dd></div>
              <div><dt>Duplicate rows</dt><dd>{p.profile.duplicate_rows}</dd></div>
              <div><dt>File size</dt><dd>{formatBytes(p.dataset.size_bytes)}</dd></div>
              <div><dt>Uploaded</dt><dd>{formatDate(p.dataset.created_at)}</dd></div>
              <div><dt>Deleted automatically</dt><dd>{p.dataset.expires_at ? formatDate(p.dataset.expires_at) : "Never"}</dd></div>
            </dl>
          </Panel>
          <Panel title="Columns" note="Select a row to see its distribution.">
            <DataTable caption="Column profile" columns={["Column", "Type", "Missing", "Distinct", "Typical value"]}
              rows={p.profile.columns.map((c) => [
                <button key="n" className="link" aria-pressed={chosen === c.name} onClick={() => setChosen(c.name)}>{c.name}</button>,
                <Badge key="k" tone={c.kind === "identifier" || c.kind === "constant" ? "warn" : "neutral"}>{c.kind.replace("_", " ")}</Badge>,
                `${c.missing} (${c.missing_pct}%)`,
                c.unique,
                c.stats ? `median ${formatNumber(c.stats.median, 2)}` : c.top_values?.[0] ? `${c.top_values[0].value} (${c.top_values[0].count})` : "n/a",
              ])} />
          </Panel>
          {col && (
            <Panel title={`Distribution of ${col.name}`}>
              {col.histogram && col.histogram.counts.length > 0 ? <Histogram edges={col.histogram.edges} counts={col.histogram.counts} label={`Histogram of ${col.name}`} />
                : col.top_values && col.top_values.length > 0 ? (
                  <DataTable columns={["Value", "Rows"]} rows={col.top_values.map((t) => [t.value, t.count])} caption={`Most common values of ${col.name}`} />
                ) : <Empty title="No distribution to show">Identifier, text and constant columns are not charted.</Empty>}
              {col.stats && <p className="muted">min {formatNumber(col.stats.min, 2)}, mean {formatNumber(col.stats.mean, 2)}, max {formatNumber(col.stats.max, 2)}, standard deviation {formatNumber(col.stats.std, 2)}</p>}
              {col.invalid_entries ? <Notice tone="warn" title="Invalid entries">{col.invalid_entries} value(s) in this mostly numeric column cannot be read as numbers.</Notice> : null}
            </Panel>
          )}
        </>
      )}
      {preview.data && (
        <Panel title="First rows" note={`Showing ${preview.data.rows.length} of ${preview.data.total_rows.toLocaleString()} rows.`}>
          <DataTable caption="Dataset preview" columns={preview.data.columns} rows={preview.data.rows.map((r) => r.map((v) => (v === null ? <span className="muted">missing</span> : String(v))))} />
        </Panel>
      )}
    </>
  );
}

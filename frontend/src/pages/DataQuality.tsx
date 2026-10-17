import { useApp } from "../state";
import { useAsync } from "../lib/useAsync";
import { Badge, DataTable, ErrorNotice, Loading, Notice, PageTitle, Panel } from "../components/ui";
import { DatasetSelect } from "../components/Pickers";
import { BarList } from "../components/charts";

const TONE = { error: "bad", warning: "warn", info: "neutral" } as const;

export default function DataQuality() {
  const { api, selection, select } = useApp();
  const id = selection.datasetId;
  const q = useAsync(() => (id ? api.quality(id) : Promise.resolve(undefined)), [api, id]);
  const r = q.data;
  const missing = (r?.columns ?? []).filter((c) => c.missing > 0).sort((a, b) => b.missing_pct - a.missing_pct);

  return (
    <>
      <PageTitle title="Data quality" lead="Problems found here are reported, not silently fixed. Invalid numbers are treated as missing during modelling." />
      <Panel title="Dataset"><DatasetSelect value={id} onChange={(d) => select({ datasetId: d })} /></Panel>
      {q.loading && id && <Loading label="Checking data" />}
      {q.error && <ErrorNotice error={q.error} onRetry={q.reload} />}
      {r && (
        <>
          <Panel title="Summary">
            <dl className="facts">
              <div><dt>Errors</dt><dd>{r.severity_counts.error}</dd></div>
              <div><dt>Warnings</dt><dd>{r.severity_counts.warning}</dd></div>
              <div><dt>Notes</dt><dd>{r.severity_counts.info}</dd></div>
              <div><dt>Missing cells</dt><dd>{r.missing_cells.toLocaleString()} ({r.missing_cells_pct}%)</dd></div>
              <div><dt>Duplicate rows</dt><dd>{r.duplicate_rows}</dd></div>
            </dl>
            {r.issues.length === 0 && <Notice tone="ok" title="No issues found">The checks found nothing to report.</Notice>}
          </Panel>
          {r.issues.length > 0 && (
            <Panel title="Findings">
              <DataTable caption="Data quality findings" columns={["Severity", "Column", "What was found"]}
                rows={r.issues.map((i) => [<Badge key="s" tone={TONE[i.severity]}>{i.severity}</Badge>, i.column ?? "All rows", i.message])} />
            </Panel>
          )}
          {missing.length > 0 && (
            <Panel title="Missing values by column">
              <BarList label="Percent missing by column" items={missing.map((c) => ({ label: c.name, value: c.missing_pct, note: `${c.missing} rows` }))} max={100} format={(v) => `${v}%`} />
            </Panel>
          )}
        </>
      )}
    </>
  );
}

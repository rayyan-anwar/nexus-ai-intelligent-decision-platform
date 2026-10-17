import { useState } from "react";
import { useApp } from "../state";
import { download } from "../lib/useAsync";
import type { AnomalyResult } from "../lib/types";
import { formatNumber, formatPercent } from "../lib/format";
import { Button, DataTable, ErrorNotice, Field, Notice, PageTitle, Panel } from "../components/ui";
import { DatasetSelect } from "../components/Pickers";
import { Histogram } from "../components/charts";

export default function Anomalies() {
  const { api, selection, select } = useApp();
  const id = selection.datasetId;
  const [level, setLevel] = useState("medium");
  const [custom, setCustom] = useState("0.05");
  const [busy, setBusy] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [res, setRes] = useState<AnomalyResult | null>(null);

  const sensitivity = (): string | number => (level === "custom" ? Number(custom) : level);

  async function run() {
    if (!id) return;
    setBusy(true); setError(null);
    try { setRes(await api.detectAnomalies(id, sensitivity())); } catch (e) { setError(e as Error); setRes(null); } finally { setBusy(false); }
  }
  async function exportCsv() {
    if (!id) return;
    setExporting(true); setError(null);
    try { download("nexus-anomalies.csv", await api.anomaliesCsv(id, sensitivity())); } catch (e) { setError(e as Error); } finally { setExporting(false); }
  }

  return (
    <>
      <PageTitle title="Anomaly detection" lead="Find records that look unusual compared with the rest of the dataset." />
      <Notice tone="warn" title="Unusual is not the same as wrong">An anomaly score does not mean fraud, an error or wrongdoing. Review flagged records with domain knowledge before acting.</Notice>
      <Panel title="Settings">
        <div className="stack">
          <DatasetSelect value={id} onChange={(d) => select({ datasetId: d })} />
          <div className="form-grid">
            <Field label="Sensitivity" hint="Roughly the share of rows to flag: low 1%, medium 3%, high 8%.">
              {(fid) => (
                <select id={fid} value={level} onChange={(e) => setLevel(e.target.value)}>
                  <option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="custom">Custom share</option>
                </select>
              )}
            </Field>
            {level === "custom" && <Field label="Share to flag" hint="Between 0.001 and 0.3">{(fid) => <input id={fid} inputMode="decimal" value={custom} onChange={(e) => setCustom(e.target.value)} />}</Field>}
          </div>
          <div className="row"><Button variant="primary" busy={busy} disabled={!id} onClick={() => void run()}>Detect anomalies</Button></div>
        </div>
      </Panel>
      {error && <ErrorNotice error={error} />}
      {res && (
        <>
          <Panel title="Results" actions={<Button busy={exporting} onClick={() => void exportCsv()}>Download flagged records (CSV)</Button>}>
            <dl className="facts">
              <div><dt>Rows scored</dt><dd>{res.n_rows.toLocaleString()}</dd></div>
              <div><dt>Flagged</dt><dd>{res.n_flagged} ({formatPercent(res.n_flagged / res.n_rows, 1)})</dd></div>
              <div><dt>Flag threshold</dt><dd>{formatNumber(res.threshold, 3)}</dd></div>
              <div><dt>Columns used</dt><dd>{res.features_used.length}</dd></div>
            </dl>
            <Histogram label="Distribution of anomaly scores" edges={res.score_histogram.edges} counts={res.score_histogram.counts} threshold={res.threshold} />
          </Panel>
          <Panel title="Most unusual records" note={`Showing ${res.flagged.length} of ${res.n_flagged} flagged. Scores run from 0 (typical) to 1 (most unusual).`}>
            <DataTable caption="Flagged records" columns={["Record", "Score", "What stands out"]}
              rows={res.flagged.map((f) => [
                f.row_id ?? `row ${f.row_index}`, formatNumber(f.score, 3),
                f.reasons.length ? f.reasons.map((r) => (r.kind === "rare_category" ? `${r.feature}: rare category` : `${r.feature}: ${formatNumber(r.robust_z, 1)} robust SD from typical`)).join("; ") : "Unusual combination of values",
              ])} />
          </Panel>
        </>
      )}
    </>
  );
}

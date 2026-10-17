import { useState } from "react";
import { useApp } from "../state";
import type { DriftLevel, DriftResult } from "../lib/types";
import { describeLevel, formatNumber, formatPercent } from "../lib/format";
import { Badge, DataTable, ErrorNotice, Field, Button, Notice, PageTitle, Panel, Warnings } from "../components/ui";
import { DatasetSelect } from "../components/Pickers";
import { BarList } from "../components/charts";

const TONE: Record<DriftLevel, "ok" | "warn" | "bad" | "neutral"> = { stable: "ok", moderate: "warn", significant: "bad", insufficient_data: "neutral" };

export default function Drift() {
  const { api, selection, select } = useApp();
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [warn, setWarn] = useState("0.1");
  const [alert, setAlert] = useState("0.25");
  const [share, setShare] = useState("0.3");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [res, setRes] = useState<DriftResult | null>(null);
  const ref = selection.datasetId;

  async function run() {
    if (!ref || !currentId) return;
    setBusy(true); setError(null);
    try {
      setRes(await api.analyzeDrift(ref, currentId, { psi_warn: Number(warn), psi_alert: Number(alert), dataset_share: Number(share) }));
    } catch (e) { setError(e as Error); setRes(null); } finally { setBusy(false); }
  }

  return (
    <>
      <PageTitle title="Data drift" lead="Compare new data with the data a model was trained on. Drift means the inputs have changed, so older predictions may be less reliable." />
      <Panel title="Datasets to compare">
        <div className="stack">
          <DatasetSelect label="Reference data (what the model learned from)" value={ref} onChange={(d) => select({ datasetId: d })} />
          <DatasetSelect label="New data (what you want to check)" value={currentId} onChange={(d) => setCurrentId(d)} />
          <div className="form-grid">
            <Field label="Moderate shift from PSI" hint="Conventional starting point: 0.1">{(id) => <input id={id} inputMode="decimal" value={warn} onChange={(e) => setWarn(e.target.value)} />}</Field>
            <Field label="Significant shift from PSI" hint="Conventional starting point: 0.25">{(id) => <input id={id} inputMode="decimal" value={alert} onChange={(e) => setAlert(e.target.value)} />}</Field>
            <Field label="Share of columns that signals dataset drift" hint="0.3 means 30% of columns">{(id) => <input id={id} inputMode="decimal" value={share} onChange={(e) => setShare(e.target.value)} />}</Field>
          </div>
          <div><Button variant="primary" busy={busy} disabled={!ref || !currentId} onClick={() => void run()}>Analyze drift</Button></div>
        </div>
      </Panel>
      {error && <ErrorNotice error={error} />}
      {res && (
        <>
          <Panel title="Verdict">
            <Notice tone={res.dataset_drift ? "warn" : "ok"} title={res.dataset_drift ? "Dataset drift detected" : "No dataset-level drift detected"}>
              {res.columns_drifted} of {res.columns_analyzed} columns shifted ({formatPercent(res.share_drifted, 0)}), compared with a threshold of {formatPercent(res.config.dataset_share, 0)}.
              Reference {res.n_reference.toLocaleString()} rows, new data {res.n_current.toLocaleString()} rows.
            </Notice>
          </Panel>
          <Panel title="Population stability index by column" note="Higher means a bigger change in the column's distribution.">
            <BarList label="PSI by column" items={res.columns.filter((c) => c.psi !== null).map((c) => ({ label: c.column, value: c.psi ?? 0, note: describeLevel(c.level) }))} format={(v) => formatNumber(v, 3)} />
          </Panel>
          <Panel title="Column details">
            <DataTable caption="Drift by column" columns={["Column", "Level", "PSI", "Adjusted p-value", "Notes"]}
              rows={res.columns.map((c) => [
                c.column,
                <Badge key="l" tone={TONE[c.level]}>{describeLevel(c.level)}</Badge>,
                formatNumber(c.psi, 3),
                c.p_value_adjusted === null ? "n/a" : formatNumber(c.p_value_adjusted, 4),
                [...(c.unseen_categories?.length ? [`New categories: ${c.unseen_categories.map((u) => `${u.value} (${formatPercent(u.share, 1)})`).join(", ")}`] : []),
                  ...(c.mean_shift_std ? [`mean moved ${formatNumber(c.mean_shift_std, 2)} SD`] : []), ...c.notes].join("; ") || "",
              ])} />
          </Panel>
          <Warnings title="Assumptions and limits" tone="info" items={res.warnings} />
        </>
      )}
    </>
  );
}

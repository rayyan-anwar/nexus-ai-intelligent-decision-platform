import { useState } from "react";
import { useApp } from "../state";
import { useAsync } from "../lib/useAsync";
import type { LocalExplanation } from "../lib/types";
import { formatNumber } from "../lib/format";
import { Badge, ErrorNotice, Loading, Notice, PageTitle, Panel, Warnings } from "../components/ui";
import { ModelSelect, RecordForm } from "../components/Pickers";
import { BarList, SignedBars } from "../components/charts";

export default function Explain() {
  const { api, selection, select } = useApp();
  const modelId = selection.modelId;
  const model = useAsync(() => (modelId ? api.getModel(modelId) : Promise.resolve(undefined)), [api, modelId]);
  const global = useAsync(() => (modelId ? api.globalExplanation(modelId) : Promise.resolve(undefined)), [api, modelId]);
  const [local, setLocal] = useState<LocalExplanation | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const g = global.data;
  const m = model.data;

  async function explain(record: Record<string, unknown>) {
    if (!modelId) return;
    setBusy(true); setError(null);
    try { setLocal(await api.localExplanation(modelId, record)); } catch (e) { setError(e as Error); setLocal(null); } finally { setBusy(false); }
  }

  return (
    <>
      <PageTitle title="Explainable AI" lead="See which inputs the model relies on. These explanations describe the model's behaviour, not what causes the outcome in the real world." />
      <Panel title="Model"><ModelSelect value={modelId} onChange={(id) => { select({ modelId: id }); setLocal(null); }} /></Panel>
      {global.loading && modelId && <Loading label="Loading importance" />}
      {global.error && <ErrorNotice error={global.error} onRetry={global.reload} />}
      {g && (
        <Panel title="What the model relies on overall" note={g.method}>
          <div className="stack">
            <BarList label="Permutation importance" items={g.importance.map((i) => ({ label: i.feature, value: i.importance, note: i.unstable ? "unstable" : undefined }))} format={(v) => formatNumber(v, 3)} />
            <p className="muted">{g.interpretation}</p>
            <Warnings title="Read with care" items={g.warnings} />
            {g.importance.some((i) => i.unstable) && <p><Badge tone="warn">unstable</Badge> marks features whose importance is within noise; do not rank them against each other.</p>}
          </div>
        </Panel>
      )}
      {m && (
        <Panel title="Why this prediction?" note="Edit the record, then explain it. Estimated by sampling, so it takes a moment.">
          <RecordForm key={m.id} features={m.schema.features} busy={busy} submitLabel="Explain this prediction" onSubmit={(r) => void explain(r)} />
        </Panel>
      )}
      {error && <ErrorNotice error={error} />}
      {local && (
        <Panel title="Contributions for this record" note={`${local.output}: starts at ${formatNumber(local.base_value, 3)} on average and ends at ${formatNumber(local.model_output, 3)} for this record.`}>
          <div className="stack">
            <SignedBars label="Feature contributions" items={local.contributions.slice(0, 12).map((c) => ({ label: `${c.feature} = ${c.value ?? "missing"}`, value: c.contribution, err: c.std_error }))} />
            <p className="muted">{local.interpretation}</p>
            <Warnings title="Input problems" items={local.issues} />
            <Notice tone="warn" title="Limits of this explanation"><ul>{local.caveats.map((c) => <li key={c}>{c}</li>)}</ul></Notice>
          </div>
        </Panel>
      )}
    </>
  );
}

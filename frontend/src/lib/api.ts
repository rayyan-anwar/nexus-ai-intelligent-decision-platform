import type {
  AnomalyResult, CompareResponse, Dataset, DriftResult, DriftThresholds, Experiment, ExperimentRequest, ExperimentSummary,
  GlobalExplanation, Health, LocalExplanation, ModelDetail, ModelSummary, PredictResponse, Preview, ProfileResponse,
  QualityReport, ServerSettings,
} from "./types";

export class ApiError extends Error {
  status: number;
  code: string;
  requestId?: string | null;
  details?: unknown;
  constructor(status: number, code: string, message: string, requestId?: string | null, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.details = details;
  }
}

export interface ApiOptions {
  baseUrl?: string;
  getToken?: () => string | null;
  fetchImpl?: typeof fetch;
}

interface ErrorDetail { loc?: string[]; message?: string }

/** Turn any failed response into an ApiError that has a message safe to show to people. */
export async function parseError(res: Response): Promise<ApiError> {
  const requestId = res.headers.get("x-request-id");
  try {
    const body = await res.json();
    const err = body?.error;
    if (err?.message) {
      const list: ErrorDetail[] = Array.isArray(err.details?.errors) ? err.details.errors : [];
      const extra = list.length ? ` (${list.slice(0, 3).map((e) => `${(e.loc ?? []).slice(1).join(".")}: ${e.message}`).join("; ")})` : "";
      return new ApiError(res.status, err.code ?? "error", err.message + extra, err.request_id ?? requestId, err.details);
    }
  } catch {
    /* fall through to the generic message */
  }
  const fallback: Record<number, string> = {
    401: "A valid API token is required. Add one under Reports and settings.",
    403: "Your token does not allow this action.",
    404: "That item was not found.",
    413: "The file is too large.",
    429: "Too many requests. Wait a moment and try again.",
  };
  return new ApiError(res.status, "http_error", fallback[res.status] ?? `The server returned an error (HTTP ${res.status}).`, requestId);
}

export function createApi(opts: ApiOptions = {}) {
  const base = (opts.baseUrl ?? "/api/v1").replace(/\/$/, "");
  const doFetch = (input: string, init?: RequestInit) => (opts.fetchImpl ?? globalThis.fetch.bind(globalThis))(input, init);

  async function raw(path: string, init: RequestInit = {}): Promise<Response> {
    const headers = new Headers(init.headers);
    const token = opts.getToken?.();
    if (token) headers.set("Authorization", `Bearer ${token}`);
    let res: Response;
    try {
      res = await doFetch(`${base}${path}`, { ...init, headers });
    } catch {
      throw new ApiError(0, "network_error", "Cannot reach the server. Check that the API is running and try again.");
    }
    if (!res.ok) throw await parseError(res);
    return res;
  }

  async function json<T>(path: string, init: RequestInit = {}): Promise<T> {
    const res = await raw(path, init);
    return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
  }

  const post = <T>(path: string, body: unknown) =>
    json<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const id = encodeURIComponent;
  const form = (f: File) => {
    const fd = new FormData();
    fd.append("file", f);
    return fd;
  };

  return {
    health: () => json<Health>("/health"),
    settings: () => json<ServerSettings>("/settings"),
    purgeExpired: () => post<{ datasets_deleted: number }>("/admin/retention/purge", {}),

    listDatasets: () => json<Dataset[]>("/datasets"),
    uploadDataset: (f: File) => json<Dataset>("/datasets/upload", { method: "POST", body: form(f) }),
    createDemoDataset: () => json<Dataset>("/datasets/demo", { method: "POST" }),
    profile: (datasetId: string) => json<ProfileResponse>(`/datasets/${id(datasetId)}/profile`),
    quality: (datasetId: string) => json<QualityReport>(`/datasets/${id(datasetId)}/quality`),
    preview: (datasetId: string, rows = 50) => json<Preview>(`/datasets/${id(datasetId)}/preview?rows=${rows}`),
    deleteDataset: (datasetId: string) => json<void>(`/datasets/${id(datasetId)}`, { method: "DELETE" }),

    startExperiment: (req: ExperimentRequest) => post<Experiment>("/experiments", req),
    listExperiments: () => json<Experiment[]>("/experiments"),
    getExperiment: (experimentId: string) => json<Experiment>(`/experiments/${id(experimentId)}`),
    metrics: (experimentId: string) => json<ExperimentSummary>(`/experiments/${id(experimentId)}/metrics`),
    compare: (ids: string[]) => json<CompareResponse>(`/experiments/compare?ids=${ids.map(id).join(",")}`),
    reportHtml: async (experimentId: string) => (await raw(`/experiments/${id(experimentId)}/report`)).text(),

    listModels: () => json<ModelSummary[]>("/models"),
    getModel: (modelId: string) => json<ModelDetail>(`/models/${id(modelId)}`),
    deleteModel: (modelId: string) => json<void>(`/models/${id(modelId)}`, { method: "DELETE" }),
    predict: (modelId: string, records: Record<string, unknown>[]) => post<PredictResponse>(`/models/${id(modelId)}/predict`, { records }),
    predictCsv: async (modelId: string, f: File) => (await raw(`/models/${id(modelId)}/predict/csv`, { method: "POST", body: form(f) })).blob(),
    globalExplanation: (modelId: string) => json<GlobalExplanation>(`/models/${id(modelId)}/explanations`),
    localExplanation: (modelId: string, record: Record<string, unknown>, targetClass?: string) =>
      post<LocalExplanation>(`/models/${id(modelId)}/explanations/local`, { record, target_class: targetClass ?? null, n_permutations: 30 }),

    detectAnomalies: (datasetId: string, sensitivity: string | number) => post<AnomalyResult>("/anomalies/detect", { dataset_id: datasetId, sensitivity }),
    anomaliesCsv: async (datasetId: string, sensitivity: string | number) =>
      (await raw("/anomalies/export", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ dataset_id: datasetId, sensitivity }) })).blob(),
    analyzeDrift: (referenceId: string, currentId: string, thresholds?: Partial<DriftThresholds>) =>
      post<DriftResult>("/drift/analyze", { reference_dataset_id: referenceId, current_dataset_id: currentId, ...(thresholds ? { thresholds } : {}) }),
  };
}

export type Api = ReturnType<typeof createApi>;

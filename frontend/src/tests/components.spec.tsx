import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App, { PAGES } from "../App";
import { RecordForm } from "../components/Pickers";
import { BarList, UncertaintyStrip } from "../components/charts";
import { ErrorNotice, Notice } from "../components/ui";
import { ApiError, type Api } from "../lib/api";
import type { FeatureSpec, ModelDetail } from "../lib/types";
import { AppProvider } from "../state";

const FEATURES: FeatureSpec[] = [
  { name: "seats", kind: "numeric", categories: null, min: 1, max: 200, median: 8, mode: null },
  { name: "plan", kind: "categorical", categories: ["basic", "premium"], min: null, max: null, median: null, mode: "basic" },
];

const MODEL: ModelDetail = {
  id: "mdl_1", experiment_id: "exp_1", name: "random_forest", task: "binary", target: "churned", created_at: "2026-01-01T00:00:00",
  primary_metric: "roc_auc", test_score: 0.7, classes: ["0", "1"], positive_label: "1", interval: null,
  schema: { features: FEATURES, target: "churned", task: "binary", classes: ["0", "1"], positive_label: "1" },
};

function mockApi(overrides: Partial<Record<keyof Api, unknown>> = {}): Api {
  const base = {
    health: vi.fn().mockResolvedValue({ status: "ok", version: "0.1.0", database: "ok" }),
    settings: vi.fn().mockResolvedValue({ version: "0.1.0", environment: "test", auth_required: false, retention_days: 30, max_upload_mb: 10, max_rows: 1000, max_cols: 50, rate_limit_per_minute: 0, native_accelerator: false, synthetic_demo_available: true }),
    listDatasets: vi.fn().mockResolvedValue([]),
    listModels: vi.fn().mockResolvedValue([MODEL]),
    listExperiments: vi.fn().mockResolvedValue([]),
    getModel: vi.fn().mockResolvedValue(MODEL),
    predict: vi.fn().mockResolvedValue({
      model: { name: "random_forest", task: "binary", target: "churned" }, n_records: 1, issues: ["1 value(s) in 'seats' were outside the training range"],
      uncertainty_note: "Probabilities are model estimates.", predictions: [{ prediction: "1", confidence: 0.55, low_confidence: true, probabilities: { "0": 0.45, "1": 0.55 } }],
    }),
  };
  return { ...base, ...overrides } as unknown as Api;
}

function renderApp(api: Api, route = "overview") {
  window.location.hash = `#/${route}`;
  return render(<AppProvider apiOverride={api}><App /></AppProvider>);
}

beforeEach(() => { sessionStorage.clear(); });

describe("ui primitives", () => {
  it("announces errors with the request id", () => {
    render(<ErrorNotice error={new ApiError(500, "internal_error", "Server broke", "req123")} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Server broke");
    expect(screen.getByRole("alert")).toHaveTextContent("req123");
  });
  it("uses a status role for non-error notices", () => {
    render(<Notice title="Heads up">Details</Notice>);
    expect(screen.getByRole("status")).toHaveTextContent("Heads up");
  });
  it("renders a bar list with accessible label", () => {
    render(<BarList label="Importance" items={[{ label: "seats", value: 0.4 }, { label: "plan", value: 0.1, note: "unstable" }]} />);
    const list = screen.getByRole("list", { name: "Importance" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(list).toHaveTextContent("unstable");
  });
});

describe("uncertainty strip", () => {
  it("shows class probabilities and flags low confidence", () => {
    render(<UncertaintyStrip task="binary" target="churned" prediction={{ prediction: "1", confidence: 0.55, low_confidence: true, probabilities: { "0": 0.45, "1": 0.55 } }} />);
    expect(screen.getByText("1", { selector: "strong" })).toBeInTheDocument();
    expect(screen.getByText(/55% estimated probability/)).toBeInTheDocument();
    expect(screen.getByText("Low confidence")).toBeInTheDocument();
  });
  it("shows a range for regression and never a bare number", () => {
    render(<UncertaintyStrip task="regression" target="spend" intervalLevel={0.9} prediction={{ prediction: 100, interval_low: 80, interval_high: 125 }} />);
    expect(screen.getByText(/plausible range 80 to 125/)).toBeInTheDocument();
    expect(screen.getByText(/about 90% coverage/)).toBeInTheDocument();
  });
  it("is honest when no interval is available", () => {
    render(<UncertaintyStrip task="regression" target="spend" prediction={{ prediction: 5 }} />);
    expect(screen.getByText(/no interval available/)).toBeInTheDocument();
  });
});

describe("record form", () => {
  it("submits typed values and maps blanks to null", async () => {
    const onSubmit = vi.fn();
    render(<RecordForm features={FEATURES} submitLabel="Predict" onSubmit={onSubmit} />);
    await userEvent.clear(screen.getByLabelText("seats"));
    await userEvent.type(screen.getByLabelText("seats"), "12");
    await userEvent.selectOptions(screen.getByLabelText("plan"), "premium");
    await userEvent.click(screen.getByRole("button", { name: "Predict" }));
    expect(onSubmit).toHaveBeenCalledWith({ seats: 12, plan: "premium" });
    await userEvent.clear(screen.getByLabelText("seats"));
    await userEvent.selectOptions(screen.getByLabelText("plan"), "");
    await userEvent.click(screen.getByRole("button", { name: "Predict" }));
    expect(onSubmit).toHaveBeenLastCalledWith({ seats: null, plan: null });
  });
  it("blocks submission and explains invalid numbers", async () => {
    const onSubmit = vi.fn();
    render(<RecordForm features={FEATURES} submitLabel="Predict" onSubmit={onSubmit} />);
    await userEvent.clear(screen.getByLabelText("seats"));
    await userEvent.type(screen.getByLabelText("seats"), "abc");
    await userEvent.click(screen.getByRole("button", { name: "Predict" }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("Fix the highlighted fields");
    expect(screen.getByLabelText("seats")).toHaveAttribute("aria-invalid", "true");
  });
});

describe("app shell", () => {
  it("lists all ten workflow pages and marks the current one", () => {
    renderApp(mockApi());
    const nav = screen.getByRole("navigation", { name: "Workflow" });
    expect(within(nav).getAllByRole("link").filter((a) => a.getAttribute("href")?.startsWith("#/") && a.textContent !== "NEXUS AI")).toHaveLength(PAGES.length);
    expect(PAGES).toHaveLength(10);
    expect(within(nav).getByRole("link", { name: "Overview" })).toHaveAttribute("aria-current", "page");
  });
  it("shows an actionable error when the API is unreachable", async () => {
    const api = mockApi({ health: vi.fn().mockRejectedValue(new ApiError(0, "network_error", "Cannot reach the server.")) });
    renderApp(api);
    expect(await screen.findByText(/Cannot reach the server/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});

describe("predictions page", () => {
  it("predicts for a record and shows uncertainty, input problems and the caveat", async () => {
    const api = mockApi();
    renderApp(api, "predictions");
    await userEvent.click(await screen.findByRole("button", { name: "Predict" }));
    await waitFor(() => expect(api.predict).toHaveBeenCalledTimes(1));
    expect(vi.mocked(api.predict).mock.calls[0][0]).toBe("mdl_1");
    expect(await screen.findByText("Low confidence")).toBeInTheDocument();
    expect(screen.getByText(/outside the training range/)).toBeInTheDocument();
    expect(screen.getByText("Probabilities are model estimates.")).toBeInTheDocument();
  });
  it("shows the server's message when prediction fails", async () => {
    const api = mockApi({ predict: vi.fn().mockRejectedValue(new ApiError(422, "invalid_prediction_input", "None of the model's input columns were provided.")) });
    renderApp(api, "predictions");
    await userEvent.click(await screen.findByRole("button", { name: "Predict" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("None of the model's input columns");
  });
  it("guides people to train a model when none exist", async () => {
    renderApp(mockApi({ listModels: vi.fn().mockResolvedValue([]) }), "predictions");
    expect(await screen.findByText("No trained models yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Go to model training" })).toBeInTheDocument();
  });
});

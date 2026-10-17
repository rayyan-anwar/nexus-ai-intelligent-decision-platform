import { useEffect, type ComponentType } from "react";
import { useApp } from "./state";
import Overview from "./pages/Overview";
import DatasetExplorer from "./pages/DatasetExplorer";
import DataQuality from "./pages/DataQuality";
import Training from "./pages/Training";
import Comparison from "./pages/Comparison";
import Predictions from "./pages/Predictions";
import Explain from "./pages/Explain";
import Anomalies from "./pages/Anomalies";
import Drift from "./pages/Drift";
import Reports from "./pages/Reports";

export const PAGES: { route: string; label: string; Component: ComponentType }[] = [
  { route: "overview", label: "Overview", Component: Overview },
  { route: "datasets", label: "Dataset explorer", Component: DatasetExplorer },
  { route: "quality", label: "Data quality", Component: DataQuality },
  { route: "training", label: "Model training", Component: Training },
  { route: "comparison", label: "Experiment comparison", Component: Comparison },
  { route: "predictions", label: "Predictions", Component: Predictions },
  { route: "explain", label: "Explainable AI", Component: Explain },
  { route: "anomalies", label: "Anomaly detection", Component: Anomalies },
  { route: "drift", label: "Data drift", Component: Drift },
  { route: "reports", label: "Reports and settings", Component: Reports },
];

export default function App() {
  const { route } = useApp();
  const page = PAGES.find((p) => p.route === route) ?? PAGES[0];
  const Page = page.Component;

  useEffect(() => {
    document.title = `${page.label} - NEXUS AI`;
    document.getElementById("main")?.focus();
  }, [page.label]);

  return (
    <div className="shell">
      <a className="skip" href="#main">Skip to content</a>
      <nav className="rail" aria-label="Workflow">
        <a className="brand" href="#/overview" aria-label="NEXUS AI home">
          <svg viewBox="0 0 32 32" width="28" height="28" aria-hidden="true"><rect width="32" height="32" rx="6" fill="currentColor" /><path d="M8 24V8l16 16V8" stroke="#fff" strokeWidth="3" fill="none" strokeLinejoin="round" /></svg>
          <span>NEXUS AI</span>
        </a>
        <ol>
          {PAGES.map((p) => (
            <li key={p.route}><a href={`#/${p.route}`} aria-current={p.route === page.route ? "page" : undefined}>{p.label}</a></li>
          ))}
        </ol>
        <p className="rail-note">Predictions are estimates, not guarantees.</p>
      </nav>
      <main id="main" tabIndex={-1}><Page /></main>
    </div>
  );
}

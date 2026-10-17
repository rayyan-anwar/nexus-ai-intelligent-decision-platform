import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createApi, type Api } from "./lib/api";

export interface Selection { datasetId: string | null; modelId: string | null; experimentId: string | null }

interface AppState {
  api: Api;
  token: string;
  setToken: (t: string) => void;
  selection: Selection;
  select: (patch: Partial<Selection>) => void;
  route: string;
  navigate: (route: string) => void;
}

const Ctx = createContext<AppState | null>(null);
const SEL_KEY = "nexus.selection";

function loadSelection(): Selection {
  try {
    const raw = JSON.parse(sessionStorage.getItem(SEL_KEY) ?? "{}");
    return { datasetId: raw.datasetId ?? null, modelId: raw.modelId ?? null, experimentId: raw.experimentId ?? null };
  } catch {
    return { datasetId: null, modelId: null, experimentId: null };
  }
}

export function routeFromHash(hash: string): string {
  const r = hash.replace(/^#\/?/, "").split("?")[0];
  return r || "overview";
}

export function AppProvider({ children, apiOverride }: { children: ReactNode; apiOverride?: Api }) {
  // The token lives in memory only (never localStorage) so an XSS bug cannot read it from storage.
  const [token, setToken] = useState("");
  const tokenRef = useRef(token);
  tokenRef.current = token;
  const api = useMemo(
    () => apiOverride ?? createApi({ baseUrl: import.meta.env.VITE_API_BASE_URL || "/api/v1", getToken: () => tokenRef.current || null }),
    [apiOverride],
  );

  const [selection, setSelection] = useState<Selection>(loadSelection);
  const select = useCallback((patch: Partial<Selection>) => {
    setSelection((prev) => {
      const next = { ...prev, ...patch };
      try {
        sessionStorage.setItem(SEL_KEY, JSON.stringify(next));
      } catch {
        /* storage unavailable: selection just won't persist */
      }
      return next;
    });
  }, []);

  const [route, setRoute] = useState(() => routeFromHash(window.location.hash));
  useEffect(() => {
    const onHash = () => setRoute(routeFromHash(window.location.hash));
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  const navigate = useCallback((r: string) => {
    window.location.hash = `#/${r}`;
  }, []);

  const value = useMemo(() => ({ api, token, setToken, selection, select, route, navigate }), [api, token, selection, select, route, navigate]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useApp must be used inside AppProvider");
  return v;
}

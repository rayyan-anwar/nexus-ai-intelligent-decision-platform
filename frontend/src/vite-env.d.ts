/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Optional absolute API base, e.g. https://api.example.com/api/v1 (default: same-origin /api/v1). */
  readonly VITE_API_BASE_URL?: string;
}

import assert from "node:assert/strict";
import { test } from "node:test";
import { ApiError, createApi, parseError } from "./api.ts";

function fakeFetch(handler: (url: string, init: RequestInit) => Response | Promise<Response>) {
  const calls: { url: string; init: RequestInit }[] = [];
  const impl = (async (url: string, init: RequestInit = {}) => {
    calls.push({ url, init });
    return handler(url, init);
  }) as unknown as typeof fetch;
  return { impl, calls };
}
const json = (body: unknown, status = 200, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", ...headers } });

test("sends the bearer token only when one is set", async () => {
  const f = fakeFetch(() => json({ status: "ok" }));
  let token: string | null = null;
  const api = createApi({ fetchImpl: f.impl, getToken: () => token });
  await api.health();
  assert.equal(new Headers(f.calls[0].init.headers).get("Authorization"), null);
  token = "abc";
  await api.health();
  assert.equal(new Headers(f.calls[1].init.headers).get("Authorization"), "Bearer abc");
});

test("parses the server error envelope into ApiError", async () => {
  const f = fakeFetch(() => json({ error: { code: "unsupported_task", message: "Target is an identifier", request_id: "r1" } }, 422));
  const api = createApi({ fetchImpl: f.impl });
  await assert.rejects(api.startExperiment({ dataset_id: "d", target: "t" }), (e: unknown) => {
    assert.ok(e instanceof ApiError);
    assert.equal(e.status, 422);
    assert.equal(e.code, "unsupported_task");
    assert.equal(e.message, "Target is an identifier");
    assert.equal(e.requestId, "r1");
    return true;
  });
});

test("includes validation details in the message", async () => {
  const body = { error: { code: "validation_error", message: "The request was not valid.", details: { errors: [{ loc: ["body", "test_size"], message: "must be <= 0.5" }] } } };
  const err = await parseError(json(body, 422));
  assert.match(err.message, /test_size: must be <= 0.5/);
});

test("falls back to readable messages for non-JSON errors", async () => {
  const f = fakeFetch(() => new Response("<html>bad gateway</html>", { status: 401 }));
  await assert.rejects(createApi({ fetchImpl: f.impl }).listDatasets(), /API token is required/);
  const g = fakeFetch(() => new Response("oops", { status: 502 }));
  await assert.rejects(createApi({ fetchImpl: g.impl }).listDatasets(), /HTTP 502/);
});

test("network failures become a friendly ApiError", async () => {
  const api = createApi({ fetchImpl: (async () => { throw new TypeError("fetch failed"); }) as unknown as typeof fetch });
  await assert.rejects(api.health(), (e: unknown) => e instanceof ApiError && e.status === 0 && /Cannot reach the server/.test(e.message));
});

test("encodes path parameters and builds the compare query", async () => {
  const f = fakeFetch(() => json({}));
  const api = createApi({ fetchImpl: f.impl });
  await api.profile("a/b?c");
  assert.equal(f.calls[0].url, "/api/v1/datasets/a%2Fb%3Fc/profile");
  await api.compare(["e1", "e2"]);
  assert.equal(f.calls[1].url, "/api/v1/experiments/compare?ids=e1,e2");
});

test("uploads use multipart form data without a manual content type", async () => {
  const f = fakeFetch(() => json({ id: "ds_1" }, 201));
  await createApi({ fetchImpl: f.impl }).uploadDataset(new File(["a,b\n1,2\n"], "x.csv", { type: "text/csv" }));
  const init = f.calls[0].init;
  assert.ok(init.body instanceof FormData);
  assert.equal(new Headers(init.headers).get("Content-Type"), null);
});

test("204 responses resolve to undefined and JSON bodies are posted", async () => {
  const f = fakeFetch((_u, init) => (init.method === "DELETE" ? new Response(null, { status: 204 }) : json({ ok: true })));
  const api = createApi({ fetchImpl: f.impl });
  assert.equal(await api.deleteDataset("ds"), undefined);
  await api.predict("m", [{ a: 1 }]);
  assert.deepEqual(JSON.parse(String(f.calls[1].init.body)), { records: [{ a: 1 }] });
  assert.equal(new Headers(f.calls[1].init.headers).get("Content-Type"), "application/json");
});

import assert from "node:assert/strict";
import { test } from "node:test";
import { describeLevel, formatBytes, formatNumber, formatPercent, humanize, sanitizeCell, toCsv, truncate } from "./format.ts";

test("formatNumber handles missing, tiny, huge and ordinary values", () => {
  assert.equal(formatNumber(null), "n/a");
  assert.equal(formatNumber(undefined), "n/a");
  assert.equal(formatNumber(NaN), "n/a");
  assert.equal(formatNumber(0.123456, 3), "0.123");
  assert.equal(formatNumber(1234.5, 1), "1,234.5");
  assert.equal(formatNumber(0), "0");
  assert.match(formatNumber(1e-5), /e-5/);
  assert.match(formatNumber(2.5e7), /e\+7/);
});

test("percent, bytes, humanize and truncate", () => {
  assert.equal(formatPercent(0.256, 1), "25.6%");
  assert.equal(formatPercent(null), "n/a");
  assert.equal(formatBytes(512), "512 B");
  assert.equal(formatBytes(2048), "2.0 KB");
  assert.equal(humanize("support_tickets_90d"), "Support tickets 90d");
  assert.equal(truncate("abcdef", 4), "abc…");
  assert.equal(truncate("abc", 4), "abc");
});

test("sanitizeCell neutralises formulas but leaves numbers alone", () => {
  for (const bad of ["=1+1", "+cmd|calc", "@SUM(A1)", "-cmd", "\tx"]) assert.ok(sanitizeCell(bad).startsWith("'"), bad);
  assert.equal(sanitizeCell("-5"), "-5");
  assert.equal(sanitizeCell(-5), "-5");
  assert.equal(sanitizeCell("hello"), "hello");
  assert.equal(sanitizeCell(null), "");
});

test("toCsv quotes special characters and sanitises cells and headers", () => {
  const csv = toCsv(["a", "=bad"], [["x,y", 'say "hi"'], ["line\nbreak", "=2+2"]]);
  assert.equal(csv, `a,'=bad\n"x,y","say ""hi"""\n"line\nbreak",'=2+2\n`);
});

test("describeLevel maps known levels", () => {
  assert.equal(describeLevel("significant"), "Significant shift");
  assert.equal(describeLevel("whatever"), "whatever");
});

import assert from "node:assert/strict";
import { test } from "node:test";
import { fraction, histogramBars, linearScale, niceTicks, signedExtent } from "./charts.ts";

test("linearScale maps domain to range, including flat domains", () => {
  const s = linearScale([0, 10], [0, 100]);
  assert.equal(s(5), 50);
  assert.equal(linearScale([10, 0], [0, 100])(2.5), 75);
  assert.equal(linearScale([3, 3], [0, 100])(3), 50);
});

test("niceTicks are monotonic, cover the extent and use round steps", () => {
  const t = niceTicks(0, 97, 5);
  assert.deepEqual(t, [0, 20, 40, 60, 80, 100]);
  assert.ok(t[0] <= 0 && t[t.length - 1] >= 97);
  assert.deepEqual(niceTicks(5, 5), [5]);
  assert.deepEqual(niceTicks(NaN, 1), []);
  const small = niceTicks(0, 0.9, 4);
  assert.ok(small.every((v, i) => i === 0 || v > small[i - 1]));
});

test("signedExtent includes error whiskers and never returns zero", () => {
  assert.equal(signedExtent([{ value: -0.2, err: 0.05 }, { value: 0.1 }]), 0.25);
  assert.equal(signedExtent([]), 1);
  assert.equal(signedExtent([{ value: 0 }]), 1);
});

test("histogramBars pairs edges with counts and fraction clamps", () => {
  assert.deepEqual(histogramBars([0, 1, 2], [3, 4]), [{ x0: 0, x1: 1, count: 3 }, { x0: 1, x1: 2, count: 4 }]);
  assert.equal(fraction(5, 0, 10), 0.5);
  assert.equal(fraction(-3, 0, 10), 0);
  assert.equal(fraction(30, 0, 10), 1);
  assert.equal(fraction(1, 2, 2), 0.5);
});

import assert from "node:assert/strict";
import test from "node:test";

import { assertReconnectHasNoOverlap } from "./event-evidence.js";

void test("resume evidence rejects duplicate SSE sequence numbers", () => {
  assert.throws(
    () => assertReconnectHasNoOverlap([1, 2], [2, 3]),
    /replayed sequence/,
  );
});

void test("resume evidence accepts events after the cursor", () => {
  assert.doesNotThrow(() => assertReconnectHasNoOverlap([1, 2], [3, 4]));
});

import assert from "node:assert/strict";
import test from "node:test";

import { stageIsolatedConsumer } from "../scripts/isolated-consumer.mjs";

test("installs and builds only the staged tarball outside FRED", async () => {
  const { evidence } = await stageIsolatedConsumer();
  assert.equal(evidence.packageIsLinked, false);
  assert.equal(evidence.sourceCheckoutReferences, 0);
  assert.match(evidence.installMode, /^offline tarball/);
  assert(evidence.outputFiles.includes("fonts/Geist.woff2"));
  assert(evidence.outputFiles.includes("fonts/Geist-Italic.woff2"));
});

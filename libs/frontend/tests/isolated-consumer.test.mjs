// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

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

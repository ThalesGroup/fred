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

import { packDesignTokens } from "../../scripts/pack-design-tokens.mjs";
import { packUi } from "../../scripts/pack-ui.mjs";
import { loadReleaseContract } from "../../scripts/release-contract.mjs";
import { sha512Integrity } from "../../scripts/release-evidence.mjs";
import { stageIsolatedReactConsumer } from "../../scripts/isolated-react-consumer.mjs";

test("published token validation consumes the already verified archive offline", async () => {
  const contract = await loadReleaseContract();
  const [{ archivePath: tokenArchivePath }, { archivePath: uiArchivePath }] =
    await Promise.all([packDesignTokens({ contract }), packUi({ contract })]);
  const result = await stageIsolatedReactConsumer({
    contract,
    publishedToken: {
      coordinate: `${contract.packages.designTokens.name}@${contract.packages.designTokens.version}`,
      integrity: await sha512Integrity(tokenArchivePath),
      registry: contract.registry,
      tarball: `${contract.registry}@fred-oss/design-tokens/-/design-tokens-${contract.packages.designTokens.version}.tgz`,
    },
    publishedTokenArchivePath: tokenArchivePath,
    uiArchivePath,
  });
  assert.equal(
    result.evidence.compatibleToken.coordinate,
    `${contract.packages.designTokens.name}@${contract.packages.designTokens.version}`,
  );
  assert.equal(result.evidence.compatibleToken.registry, contract.registry);
});

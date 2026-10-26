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
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

import { parse } from "yaml";

import {
  CI_INPUT_PATTERNS,
  FONT_SOURCES,
  IFRAME_HOST_COMPATIBILITY_PATHS,
  IFRAME_SDK_CANONICAL_SOURCE_PATH,
  IFRAME_SDK_SOURCE_PATHS,
  PACKAGE_WORKSPACE_PATTERN,
  PUBLISH_WORKFLOW_PATH,
  RELEASE_TOOLING_INPUTS,
  ROOT_LICENSE_PATH,
  TOKEN_SOURCE_PATHS,
  UI_COMPONENT_SOURCE_PATHS,
  UI_FONT_SOURCE,
  UI_REACT_BASELINE_PATHS,
  UI_STYLE_SUPPORT_PATHS,
  VALIDATION_ORCHESTRATION_PATHS,
} from "../scripts/package-inputs.mjs";
import { workspaceRoot } from "../scripts/pack-design-tokens.mjs";

const repositoryRoot = path.resolve(workspaceRoot, "../..");
const workflow = parse(
  await readFile(
    path.join(repositoryRoot, ".github/workflows/Check-pending-requests.yml"),
    "utf8",
  ),
);
const publishWorkflowSource = await readFile(
  path.join(repositoryRoot, PUBLISH_WORKFLOW_PATH),
  "utf8",
);
const publishWorkflow = parse(publishWorkflowSource);
const changeStep = workflow.jobs["detect-changes"].steps.find(
  ({ id }) => id === "changes",
);
const filters = parse(changeStep.with.filters);
const packagePatterns = filters["frontend-packages"];
const frontendPatterns = filters.frontend;

function matches(changedPath, pattern) {
  if (pattern.endsWith("/**")) {
    return changedPath.startsWith(pattern.slice(0, -3));
  }
  return changedPath === pattern;
}

function selectsPackageJob(changedPaths) {
  return changedPaths.some((changedPath) =>
    packagePatterns.some((pattern) => matches(changedPath, pattern)),
  );
}

function selectsFrontendJob(changedPaths) {
  return changedPaths.some((changedPath) =>
    frontendPatterns.some((pattern) => matches(changedPath, pattern)),
  );
}

test("CI filter exactly covers the declared package input contract", () => {
  assert.deepEqual(packagePatterns, CI_INPUT_PATTERNS);
  assert.equal(
    workflow.jobs["frontend-package-checks"].if.includes("frontend-packages"),
    true,
  );
});

test("producer workspace changes select package validation", () => {
  assert(
    selectsPackageJob([
      PACKAGE_WORKSPACE_PATTERN.replace("**", "scripts/new-check.mjs"),
    ]),
  );
});

test("every release-readiness input selects package validation", () => {
  for (const sourcePath of RELEASE_TOOLING_INPUTS) {
    assert(selectsPackageJob([sourcePath]), sourcePath);
  }
  const releaseJob = workflow.jobs["frontend-package-release-readiness"];
  assert(releaseJob.if.includes("frontend-packages"));
  assert.equal(
    releaseJob.steps.find((step) => step.name === "Setup release Node.js").with[
      "node-version"
    ],
    "24.21.0",
  );
  assert(
    releaseJob.steps.some(
      (step) => step.run === "npm install --global npm@11.19.0",
    ),
  );
});

test("inventory, policy, baseline, records, changelogs, and manifests select release validation", () => {
  for (const sourcePath of [
    "libs/frontend/release/package-inventory.json",
    "libs/frontend/release/proposed-release-contract.json",
    "libs/frontend/release/compatibility-baselines.json",
    "libs/frontend/release/release-record.schema.json",
    "libs/frontend/design-tokens/CHANGELOG.md",
    "libs/frontend/ui/CHANGELOG.md",
    "libs/frontend/iframe-sdk/CHANGELOG.md",
    "libs/frontend/iframe-sdk/package.json",
    "libs/frontend/package-lock.json",
  ])
    assert(selectsPackageJob([sourcePath]), sourcePath);
  assert(!selectsPackageJob(["apps/frontend/src/rework/unrelated-page.tsx"]));
});

test("shared release tooling and compatibility inputs select CI", () => {
  for (const sourcePath of [
    "libs/frontend/scripts/npm-release.mjs",
    "libs/frontend/scripts/provision-compatible-token.mjs",
    "libs/frontend/scripts/isolated-react-consumer.mjs",
    "libs/frontend/scripts/fixture-transfer-validation.mjs",
    "libs/frontend/tests/npm-release.test.mjs",
    "libs/frontend/tests/provision-compatible-token.test.mjs",
    "libs/frontend/fixtures/release-fourth-package.json",
    "libs/frontend/Makefile",
    "libs/frontend/package-lock.json",
  ])
    assert(selectsPackageJob([sourcePath]), sourcePath);
  assert(!selectsPackageJob(["apps/frontend/src/rework/unrelated-page.tsx"]));
  assert.equal(
    publishWorkflow.on.workflow_dispatch.inputs.operation.default,
    "prepare",
  );
  assert.deepEqual(
    publishWorkflow.on.workflow_dispatch.inputs.package.options,
    ["design-tokens", "ui", "iframe-sdk"],
  );
});

test("the governing frontend packaging RFC selects release validation", () => {
  assert(selectsPackageJob(["docs/swift/FRED-FRONTEND-PACKAGING-RFC.md"]));
});

test("release-readiness CI provisions isolated consumers before tests", () => {
  const steps = workflow.jobs["frontend-package-release-readiness"].steps;
  const producerInstallIndex = steps.findIndex(
    (step) =>
      step.name === "Install producer dependencies" &&
      step.run === "npm ci" &&
      step["working-directory"] === "libs/frontend",
  );
  const consumerProvisionIndex = steps.findIndex(
    (step) =>
      step.name === "Provision isolated consumer cache" &&
      step.run === "make consumer-provision" &&
      step["working-directory"] === "libs/frontend",
  );
  const consumerDependentTestIndex = steps.findIndex(
    (step) => step.run === "make code-quality test pack-check",
  );

  assert.notEqual(producerInstallIndex, -1);
  assert.notEqual(consumerProvisionIndex, -1);
  assert.notEqual(consumerDependentTestIndex, -1);
  assert(producerInstallIndex < consumerProvisionIndex);
  assert(consumerProvisionIndex < consumerDependentTestIndex);
});

test("release workflow is a thin manual adapter with isolated publishing authority", () => {
  assert.deepEqual(Object.keys(publishWorkflow.on), ["workflow_dispatch"]);
  const publication = publishWorkflow.on.workflow_dispatch.inputs.operation;
  assert.equal(publication.default, "prepare");
  assert.deepEqual(publication.options, [
    "prepare",
    "publish",
    "verify",
    "promote",
  ]);
  assert.deepEqual(Object.keys(publishWorkflow.jobs), [
    "authorize",
    "prepare",
    "release-directory",
    "publish",
    "read-only",
    "promote-dry-run",
    "promote",
  ]);
  assert.deepEqual(publishWorkflow.permissions, { contents: "read" });
  for (const [name, job] of Object.entries(publishWorkflow.jobs)) {
    if (name === "publish") continue;
    assert.equal(job.permissions?.["id-token"], undefined, name);
  }
  const protectedJob = publishWorkflow.jobs.publish;
  assert.equal(protectedJob.environment, "npm-publish");
  assert.deepEqual(protectedJob.concurrency, {
    group: "frontend-npm-publish-${{ inputs.package }}",
    "cancel-in-progress": false,
  });
  assert.deepEqual(protectedJob.permissions, {
    contents: "read",
    "id-token": "write",
  });
  const promotionSetup = publishWorkflow.jobs.promote.steps.find(
    (step) => step.uses === "actions/setup-node@v4",
  );
  assert.equal(
    promotionSetup.with["registry-url"],
    "https://registry.npmjs.org",
  );
  const promotionDryRun = publishWorkflow.jobs["promote-dry-run"];
  assert.equal(promotionDryRun.environment, undefined);
  assert.equal(
    JSON.stringify(promotionDryRun).includes("secrets.NPM_TOKEN"),
    false,
  );
  assert(
    promotionDryRun.steps.some(
      (step) =>
        step.run ===
        'make promote PACKAGE="${{ inputs.package }}" VERSION="${{ inputs.version }}" CHANNEL="${{ inputs.channel }}" AUTH_MODE=token DRY_RUN=1',
    ),
  );
  assert(
    protectedJob.steps.some(
      (step) =>
        step.run === "npm ci --ignore-scripts" &&
        step["working-directory"] === "libs/frontend",
    ),
  );
  assert(
    protectedJob.steps.some(
      (step) =>
        step.run ===
        'make publish PACKAGE="${{ inputs.package }}" RELEASE_DIR=target/release AUTH_MODE=oidc',
    ),
  );
  assert(
    publishWorkflow.jobs.prepare.steps.some(
      (step) =>
        step.run === 'make prepare-release PACKAGE="${{ inputs.package }}"',
    ),
  );
  assert(
    publishWorkflow.jobs["release-directory"].steps.some(
      (step) => step.uses === "actions/download-artifact@v4",
    ),
  );
  for (const retired of [
    "candidate-ref",
    "attempt-refs",
    "terminal-refs",
    "release-publisher.mjs",
    "release-artifact.mjs",
    "NPM_BOOTSTRAP_TOKEN",
  ])
    assert.equal(publishWorkflowSource.includes(retired), false, retired);
});

test("preparation transfers one generated release directory to later operations", () => {
  const producer = publishWorkflow.jobs.prepare;
  const receiver = publishWorkflow.jobs["release-directory"];
  assert.equal(producer.needs, "authorize");
  assert.deepEqual(receiver.needs, ["authorize", "prepare"]);
  assert.equal(
    producer.steps.find((step) => step.uses === "actions/setup-node@v4").with[
      "node-version"
    ],
    "24.21.0",
  );
  assert(
    producer.steps.some(
      (step) => step.run === "npm install --global npm@11.19.0",
    ),
  );
  assert(
    producer.steps.some((step) => step.name === "Prepare the selected package"),
  );
  assert(
    producer.steps.some(
      (step) =>
        step.uses === "actions/upload-artifact@v4" &&
        step.with.name === "frontend-npm-release-${{ inputs.package }}" &&
        step.with.path ===
          "libs/frontend/target/releases/${{ inputs.package }}",
    ),
  );
  assert(
    receiver.steps.some(
      (step) =>
        step.uses === "actions/download-artifact@v4" &&
        step.with.name === "frontend-npm-release-${{ inputs.package }}" &&
        step.with["run-id"].includes("prepared-run-id"),
    ),
  );
  assert(
    receiver.steps.some((step) => step.name === "Resolve generated metadata"),
  );
  const resolver = receiver.steps.find(
    (step) => step.name === "Resolve generated metadata",
  ).run;
  assert(resolver.includes('test "${#metadata_files[@]}" -eq 1'));
  assert(resolver.includes(".preparedBy =="));
  assert(
    resolver.includes(
      'test "${release_dir}" = "target/releases/${{ inputs.package }}/${version}"',
    ),
  );
  assert(
    resolver.includes(
      'git merge-base --is-ancestor "${source_commit}" "${GITHUB_SHA}"',
    ),
  );
});

test("retired configuration deletion selects regressions but is not a live input", () => {
  for (const filename of [
    "libs/frontend/release/bootstrap-recovery.json",
    "libs/frontend/release/registry-verification-continuation.json",
  ]) {
    assert(selectsPackageJob([filename]), filename);
    assert.equal(RELEASE_TOOLING_INPUTS.includes(filename), false, filename);
  }
  assert(
    RELEASE_TOOLING_INPUTS.includes(
      "libs/frontend/scripts/registry-verifier.mjs",
    ),
  );
});

test("CI transfers one same-run fixture set from release to application tooling", () => {
  const producer = workflow.jobs["frontend-package-release-readiness"];
  const receiver = workflow.jobs["frontend-package-checks"];
  assert.deepEqual(receiver.needs, [
    "detect-changes",
    "frontend-package-release-readiness",
  ]);
  const artifactName =
    "frontend-packages-fixture-${{ github.event.pull_request.head.sha }}-${{ github.run_id }}-${{ github.run_attempt }}";
  const createIndex = producer.steps.findIndex(
    (step) =>
      step.run === "make fixture-transfer-create" &&
      step["working-directory"] === "libs/frontend",
  );
  const producerRegressionIndex = producer.steps.findIndex(
    (step) => step.run === "make code-quality test pack-check",
  );
  const uploadIndex = producer.steps.findIndex(
    (step) =>
      step.uses === "actions/upload-artifact@v4" &&
      step.with.name === artifactName &&
      step.with.path === "libs/frontend/target/fixture-transfer" &&
      step.with["if-no-files-found"] === "error" &&
      step.with["retention-days"] === 7,
  );
  const downloadIndex = receiver.steps.findIndex(
    (step) =>
      step.uses === "actions/download-artifact@v4" &&
      step.with.name === artifactName &&
      step.with.path === "libs/frontend/target/fixture-transfer",
  );
  const receiverProvisionIndex = receiver.steps.findIndex(
    (step) => step.run === "make consumer-provision",
  );
  const browserProvisionIndex = receiver.steps.findIndex(
    (step) => step.run === "make browser-install",
  );
  const validationIndex = receiver.steps.findIndex(
    (step) =>
      step.run === "make fixture-transfer-validate" &&
      step["working-directory"] === "libs/frontend",
  );
  const finalEvidenceIndex = receiver.steps.findIndex(
    (step) =>
      step.uses === "actions/upload-artifact@v4" &&
      step.with.name ===
        "frontend-packages-fixture-validation-${{ github.event.pull_request.head.sha }}-${{ github.run_id }}-${{ github.run_attempt }}" &&
      step.with.path ===
        "libs/frontend/target/fixture-validation/final-evidence.json" &&
      step.with["if-no-files-found"] === "error" &&
      step.with["retention-days"] === 7,
  );

  for (const index of [
    createIndex,
    producerRegressionIndex,
    uploadIndex,
    downloadIndex,
    receiverProvisionIndex,
    browserProvisionIndex,
    validationIndex,
    finalEvidenceIndex,
  ])
    assert.notEqual(index, -1);
  assert(producerRegressionIndex < createIndex && createIndex < uploadIndex);
  assert(receiverProvisionIndex < validationIndex);
  assert(browserProvisionIndex < validationIndex);
  assert(
    downloadIndex < validationIndex && validationIndex < finalEvidenceIndex,
  );
  assert.equal(
    receiver.steps.some((step) =>
      [
        "make pack-check",
        "make host-integration",
        "make isolated-consumer",
        "make browser-smoke",
      ].includes(step.run),
    ),
    false,
  );
});

test("every consumed canonical stylesheet selects package validation", () => {
  for (const sourcePath of TOKEN_SOURCE_PATHS) {
    assert(selectsPackageJob([sourcePath]), sourcePath);
  }
  assert(selectsPackageJob(["apps/frontend/src/styles/index.css"]));
});

test("every packaged Geist asset selects package validation", () => {
  for (const { sourcePath } of FONT_SOURCES) {
    assert(selectsPackageJob([sourcePath]), sourcePath);
  }
});

test("every canonical UI source and style input selects package validation", () => {
  for (const sourcePath of [
    ...UI_COMPONENT_SOURCE_PATHS,
    ...UI_STYLE_SUPPORT_PATHS,
  ]) {
    assert(selectsPackageJob([sourcePath]), sourcePath);
  }
});

test("Material Symbols and React baseline inputs select package validation", () => {
  assert(selectsPackageJob([UI_FONT_SOURCE.sourcePath]));
  for (const sourcePath of UI_REACT_BASELINE_PATHS)
    assert(selectsPackageJob([sourcePath]), sourcePath);
});

test("license and validation orchestration changes select package validation", () => {
  assert(selectsPackageJob([ROOT_LICENSE_PATH]));
  for (const orchestrationPath of VALIDATION_ORCHESTRATION_PATHS) {
    assert(selectsPackageJob([orchestrationPath]), orchestrationPath);
  }
});

test("every SDK producer and canonical source selects package validation", () => {
  for (const sourcePath of IFRAME_SDK_SOURCE_PATHS) {
    assert(selectsPackageJob([sourcePath]), sourcePath);
  }
});

test("canonical protocol and declared host compatibility inputs select both gates", () => {
  assert.equal(
    IFRAME_HOST_COMPATIBILITY_PATHS[0],
    IFRAME_SDK_CANONICAL_SOURCE_PATH,
  );
  for (const sourcePath of IFRAME_HOST_COMPATIBILITY_PATHS) {
    assert(selectsPackageJob([sourcePath]), sourcePath);
    assert(selectsFrontendJob([sourcePath]), sourcePath);
  }
});

test("resolved theme and locale owners select SDK and host validation", () => {
  for (const owner of [
    "apps/frontend/src/app/ApplicationContextStruct.tsx",
    "apps/frontend/src/app/ApplicationContextProvider.tsx",
    "apps/frontend/src/i18n.ts",
  ]) {
    assert(selectsPackageJob([owner]), owner);
    assert(selectsFrontendJob([owner]), owner);
  }
  assert(!selectsPackageJob(["apps/frontend/src/rework/unrelated-page.tsx"]));
});

test("frontend-package CI runs transferred archives with application-owned host dependencies", () => {
  const steps = workflow.jobs["frontend-package-checks"].steps;
  assert(
    steps.some(
      (step) =>
        step.run === "npm ci" && step["working-directory"] === "apps/frontend",
    ),
  );
  assert(
    steps.some(
      (step) =>
        step.run === "make fixture-transfer-validate" &&
        step["working-directory"] === "libs/frontend",
    ),
  );
});

test("an unrelated application-only change may skip package validation", () => {
  assert.equal(
    selectsPackageJob(["apps/frontend/src/components/Unrelated.tsx"]),
    false,
  );
  assert(selectsFrontendJob(["apps/frontend/src/components/Unrelated.tsx"]));
});

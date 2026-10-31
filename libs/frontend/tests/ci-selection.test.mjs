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
  publishWorkflowPath,
  resolveSelectedWorkflowRun,
  validatePromotionInputs,
  validateReleaseOrigin,
  validateWorkflowInputs,
} from "../../../.github/scripts/frontend-release-workflow.mjs";
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

function normalizedCondition(job) {
  return job.if.replaceAll(/\s+/g, " ").trim();
}

function releaseDirectoryRuns({ authorize, operation, prepare }) {
  return (
    authorize === "success" &&
    ["publish", "verify"].includes(operation) &&
    ["success", "skipped"].includes(prepare)
  );
}

function downstreamRuns({
  authorize,
  cancelled = false,
  dryRun,
  operation,
  releaseDirectory,
}) {
  const allowed =
    !cancelled && authorize === "success" && releaseDirectory === "success";
  return {
    publish: allowed && operation === "publish" && !dryRun,
    readOnly:
      allowed &&
      (operation === "verify" || (operation === "publish" && dryRun)),
  };
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
    ".github/scripts/frontend-release-workflow.mjs",
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

test("the package release guide selects release validation", () => {
  assert(selectsPackageJob(["libs/frontend/RELEASE.md"]));
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
        step.run === "make promote" &&
        step.env.AUTH_MODE === "token" &&
        step.env.DRY_RUN === "1" &&
        step.env.PACKAGE === "${{ inputs.package }}" &&
        step.env.VERSION === "${{ inputs.version }}" &&
        step.env.CHANNEL === "${{ inputs.channel }}",
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
        step.run === "make publish" &&
        step.env.AUTH_MODE === "oidc" &&
        step.env.PACKAGE === "${{ inputs.package }}" &&
        step.env.RELEASE_DIR === "target/release",
    ),
  );
  assert(
    publishWorkflow.jobs.prepare.steps.some(
      (step) =>
        step.run === "make prepare-release" &&
        step.env.PACKAGE === "${{ inputs.package }}",
    ),
  );
  assert.equal(
    publishWorkflow.jobs.prepare.steps.some(
      (step) => step["working-directory"] === "apps/frontend",
    ),
    false,
  );
  const readOnly = publishWorkflow.jobs["read-only"];
  assert.equal(readOnly.permissions["id-token"], undefined);
  for (const jobName of ["publish", "read-only"]) {
    const checkout = publishWorkflow.jobs[jobName].steps.find(
      (step) => step.uses === "actions/checkout@v4",
    );
    assert.equal(checkout.with.ref, "${{ github.sha }}", jobName);
    assert.equal(
      JSON.stringify(checkout).includes("source_commit"),
      false,
      jobName,
    );
  }
  const readOnlyOperation = readOnly.steps.find(
    (step) => step.name === "Verify or dry-run publication",
  );
  assert.equal(readOnlyOperation.env.AUTH_MODE, "oidc");
  assert.equal(readOnlyOperation.run.includes("AUTH_MODE="), false);
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

test("promotion inputs remain data across the workflow and Make boundary", () => {
  assert.deepEqual(
    validatePromotionInputs({
      version: "12.3.4-alpha.1+build.5",
      channel: "next-2026.10",
    }),
    { version: "12.3.4-alpha.1+build.5", channel: "next-2026.10" },
  );
  for (const value of [
    "0.1.1$(printf injected)",
    '0.1.1"; printf injected; : "',
    "0.1.1\nprintf injected",
    "$(shell printf injected)",
  ]) {
    assert.throws(
      () => validatePromotionInputs({ version: value, channel: "latest" }),
      /version must be an exact semantic version/,
    );
    assert.throws(
      () => validatePromotionInputs({ version: "0.1.1", channel: value }),
      /channel is invalid/,
    );
  }
  assert.throws(
    () =>
      validatePromotionInputs({
        version: "999999999999999999999.1.1",
        channel: "latest",
      }),
    /version must be an exact semantic version/,
  );
  assert.deepEqual(
    validatePromotionInputs({ version: "1.2.3", channel: "1.2.3-01" }),
    { version: "1.2.3", channel: "1.2.3-01" },
  );
  for (const channel of ["x.0", "1.x.0", "0.x.1-alpha"])
    assert.throws(
      () => validatePromotionInputs({ version: "1.2.3", channel }),
      /channel must not be a semantic-version range/,
    );
  const authorization = publishWorkflow.jobs.authorize.steps.find(
    (step) => step.name === "Validate source and inputs",
  );
  assert(authorization.run.includes("validate-inputs"));
  assert.equal(authorization.env.PACKAGE, "${{ inputs.package }}");
  for (const job of Object.values(publishWorkflow.jobs))
    for (const step of job.steps ?? [])
      if (step.run)
        assert.equal(
          step.run.includes("${{ inputs.package }}"),
          false,
          `${job.name ?? "job"} inserts package input into shell source`,
        );
  assert.deepEqual(
    validateWorkflowInputs({
      operation: "prepare",
      packageName: "iframe-sdk",
    }),
    { operation: "prepare", packageName: "iframe-sdk" },
  );
  assert.throws(
    () =>
      validateWorkflowInputs({
        operation: "prepare",
        packageName: "not-a-package",
      }),
    /package is invalid/,
  );
  for (const channel of ["1", "1.2", "1.2.3", "1.x", "v1.2.3"])
    assert.throws(
      () => validatePromotionInputs({ version: "1.2.3", channel }),
      /semantic-version range/,
    );
  for (const jobName of ["promote-dry-run", "promote"]) {
    const step = publishWorkflow.jobs[jobName].steps.find(
      (candidate) => candidate.run === "make promote",
    );
    assert.equal(step.run.includes("inputs.version"), false, jobName);
    assert.equal(step.run.includes("inputs.channel"), false, jobName);
    assert.equal(step.env.VERSION, "${{ inputs.version }}", jobName);
    assert.equal(step.env.CHANNEL, "${{ inputs.channel }}", jobName);
  }
});

test("publication and verification explicitly handle skipped preparation", () => {
  const releaseDirectory = publishWorkflow.jobs["release-directory"];
  assert(
    normalizedCondition(releaseDirectory).startsWith(
      "always() && !cancelled() &&",
    ),
  );
  assert.equal(
    releaseDirectoryRuns({
      authorize: "success",
      operation: "publish",
      prepare: "success",
    }),
    true,
  );
  assert.equal(
    releaseDirectoryRuns({
      authorize: "success",
      operation: "publish",
      prepare: "skipped",
    }),
    true,
  );
  const publishCondition = normalizedCondition(publishWorkflow.jobs.publish);
  const readOnlyCondition = normalizedCondition(
    publishWorkflow.jobs["read-only"],
  );
  for (const condition of [publishCondition, readOnlyCondition]) {
    assert(condition.startsWith("always() && !cancelled() &&"));
    assert(condition.includes("needs.authorize.result == 'success'"));
    assert(condition.includes("needs.release-directory.result == 'success'"));
  }
  assert.deepEqual(
    downstreamRuns({
      authorize: "success",
      dryRun: false,
      operation: "publish",
      releaseDirectory: "success",
    }),
    { publish: true, readOnly: false },
  );
  assert.deepEqual(
    downstreamRuns({
      authorize: "success",
      dryRun: false,
      operation: "verify",
      releaseDirectory: "success",
    }),
    { publish: false, readOnly: true },
  );
  assert.deepEqual(
    downstreamRuns({
      authorize: "success",
      dryRun: true,
      operation: "publish",
      releaseDirectory: "success",
    }),
    { publish: false, readOnly: true },
  );
  for (const blocked of [
    { authorize: "failure", releaseDirectory: "success" },
    { authorize: "success", releaseDirectory: "failure" },
    { authorize: "success", releaseDirectory: "success", cancelled: true },
  ])
    assert.deepEqual(
      downstreamRuns({
        ...blocked,
        dryRun: false,
        operation: "publish",
      }),
      { publish: false, readOnly: false },
    );
});

test("selected artifact origin comes from one targeted workflow-run lookup", async () => {
  const sourceCommit = "a".repeat(40);
  const run = {
    id: 41,
    path: publishWorkflowPath,
    head_branch: "swift",
    head_sha: sourceCommit,
    repository: { full_name: "ThalesGroup/fred" },
    head_repository: { full_name: "ThalesGroup/fred" },
  };
  const calls = [];
  const resolve = (overrides = {}) =>
    resolveSelectedWorkflowRun({
      github: {
        rest: {
          actions: {
            getWorkflowRun: async (request) => {
              calls.push(request);
              return { data: { ...run, ...overrides } };
            },
          },
        },
      },
      owner: "ThalesGroup",
      repo: "fred",
      runId: "41",
    });
  assert.deepEqual(await resolve(), {
    repository: "ThalesGroup/fred",
    workflow:
      "ThalesGroup/fred/.github/workflows/Publish-frontend-packages.yml@refs/heads/swift",
    runId: "41",
    sourceCommit,
  });
  assert.deepEqual(calls, [{ owner: "ThalesGroup", repo: "fred", run_id: 41 }]);
  for (const forged of [
    { id: 42 },
    { path: ".github/workflows/other.yml" },
    { head_branch: "feature" },
    { head_sha: "not-a-commit" },
    { repository: { full_name: "other/fred" } },
    { head_repository: { full_name: "fork/fred" } },
  ])
    await assert.rejects(resolve(forged));

  const identity = await resolve();
  const metadata = {
    sourceCommit,
    preparedBy: {
      kind: "github-actions",
      repository: identity.repository,
      workflow: identity.workflow,
      runId: identity.runId,
    },
  };
  assert.equal(validateReleaseOrigin({ metadata, identity }), sourceCommit);
  for (const forged of [
    {
      ...metadata,
      sourceCommit: "b".repeat(40),
    },
    {
      ...metadata,
      preparedBy: { ...metadata.preparedBy, workflow: "forged/workflow" },
    },
    {
      ...metadata,
      preparedBy: { ...metadata.preparedBy, runId: "42" },
    },
  ])
    assert.throws(() => validateReleaseOrigin({ metadata: forged, identity }));

  const receiver = publishWorkflow.jobs["release-directory"];
  const originStep = receiver.steps.find(
    (step) => step.name === "Resolve the selected workflow run",
  );
  assert.equal(originStep.uses, "actions/github-script@v7");
  assert(originStep.with.script.includes("resolveSelectedWorkflowRun"));
  const metadataStep = receiver.steps.find(
    (step) => step.name === "Resolve generated metadata",
  );
  assert.equal(
    metadataStep.env.EXPECTED_SOURCE_COMMIT,
    "${{ steps.selected-run.outputs.source_commit }}",
  );
  assert(
    metadataStep.run.includes(
      "frontend-release-workflow.mjs validate-release-origin",
    ),
  );
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
  assert(resolver.includes("validate-release-origin"));
  assert(
    resolver.includes(
      'test "${release_dir}" = "target/releases/${PACKAGE}/${version}"',
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

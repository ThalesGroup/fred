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

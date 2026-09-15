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
const recoveryPlan = JSON.parse(
  await readFile(
    path.join(repositoryRoot, "libs/frontend/release/bootstrap-recovery.json"),
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

test("manual publication workflow is branch-guarded and disabled by default", () => {
  assert.deepEqual(Object.keys(publishWorkflow.on), ["workflow_dispatch"]);
  const publication = publishWorkflow.on.workflow_dispatch.inputs.publication;
  assert.equal(publication.default, "prepare-only");
  assert.deepEqual(publication.options, [
    "prepare-only",
    "publish-bootstrap",
    "recover-bootstrap",
    "verify-existing",
  ]);
  assert.equal(
    publishWorkflow.jobs["authorize-source"].steps[0].run,
    'test "${GITHUB_REF}" = "refs/heads/swift"',
  );
  const publish = publishWorkflow.jobs["publish-bootstrap"];
  assert.equal(publish.if, "inputs.publication == 'publish-bootstrap'");
  assert.equal(publish.environment, "npm-publish");
  assert.equal(publish.permissions["id-token"], "write");
  const recovery = publishWorkflow.jobs["publish-bootstrap-recovery"];
  assert.equal(recovery.if, "inputs.publication == 'recover-bootstrap'");
  assert.equal(recovery.environment, "npm-publish");
  assert.equal(recovery.permissions["id-token"], "write");
});

test("verification continuation schedules no candidate or publication work", () => {
  const prepare = publishWorkflow.jobs["prepare-registry-verification"];
  const verify = publishWorkflow.jobs["verify-public-registry"];
  assert.equal(prepare.needs, "authorize-source");
  assert.equal(prepare.if, "inputs.publication == 'verify-existing'");
  assert.deepEqual(prepare.permissions, { actions: "read", contents: "read" });
  assert.equal(prepare.environment, undefined);
  assert.equal(prepare.permissions["id-token"], undefined);
  assert.match(verify.if, /inputs\.publication == 'verify-existing'/);
  assert.match(
    verify.if,
    /needs\.prepare-registry-verification\.result == 'success'/,
  );
  assert.deepEqual(verify.permissions, { contents: "read" });
  assert.equal(verify.environment, undefined);
  assert.equal(verify.permissions["id-token"], undefined);
  assert.equal(
    publishWorkflow.jobs["prepare-candidate"].if,
    "inputs.publication == 'prepare-only' || inputs.publication == 'publish-bootstrap'",
  );
  assert.equal(
    publishWorkflow.jobs["validate-application-compatibility"].if,
    "inputs.publication == 'prepare-only' || inputs.publication == 'publish-bootstrap'",
  );
  for (const name of ["publish-bootstrap", "publish-bootstrap-recovery"])
    assert.doesNotMatch(
      publishWorkflow.jobs[name].if,
      /verify-existing/,
      `${name} must not run for verification continuation`,
    );
  assert.equal(
    publishWorkflowSource.includes(
      "frontend-packages-registry-verification-${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}",
    ),
    true,
  );
  const retrieve = prepare.steps.find(
    (step) => step.name === "Retrieve the exact recovery artifact",
  );
  assert.match(retrieve.run, /actions\/artifacts\/10363547296\/zip/);
  assert.match(
    retrieve.run,
    /fe008c951be747cc496e9c82adf4f54f8ecd4d5c8c8bdbbf9dbda1d2a34e86b8/,
  );
  assert.equal(
    JSON.stringify([...prepare.steps, ...verify.steps]).includes(
      "NPM_BOOTSTRAP_TOKEN",
    ),
    false,
  );
  assert.equal(
    [...prepare.steps, ...verify.steps].some((step) =>
      [
        "make release-transfer-create",
        "make release-transfer-validate",
      ].includes(step.run),
    ),
    false,
  );
});

test("bootstrap token is referenced only by the mutually exclusive publication steps", () => {
  assert.equal(
    (publishWorkflowSource.match(/NPM_BOOTSTRAP_TOKEN/g) ?? []).length,
    2,
  );
  const secretSteps = ["publish-bootstrap", "publish-bootstrap-recovery"].map(
    (jobName) =>
      publishWorkflow.jobs[jobName].steps.find(
        (step) =>
          step.env?.NODE_AUTH_TOKEN === "${{ secrets.NPM_BOOTSTRAP_TOKEN }}",
      ),
  );
  assert.deepEqual(
    secretSteps.map(({ name }) => name),
    [
      "Publish the initial package versions",
      "Publish only the missing initial package versions",
    ],
  );
  for (const [jobName, job] of Object.entries(publishWorkflow.jobs)) {
    for (const step of job.steps)
      if (!secretSteps.includes(step))
        assert.equal(
          JSON.stringify(step).includes("NPM_BOOTSTRAP_TOKEN"),
          false,
          `${jobName}.${step.name}`,
        );
  }
});

test("partial-bootstrap recovery reuses the exact incident artifact without rebuilding", () => {
  const prepare = publishWorkflow.jobs["prepare-bootstrap-recovery"];
  const publish = publishWorkflow.jobs["publish-bootstrap-recovery"];
  const verify = publishWorkflow.jobs["verify-public-registry"];
  assert.equal(prepare.needs, "authorize-source");
  assert.equal(prepare.if, "inputs.publication == 'recover-bootstrap'");
  assert.equal(publish.needs, "prepare-bootstrap-recovery");
  assert.equal(publish.if, "inputs.publication == 'recover-bootstrap'");
  const retrieval = prepare.steps.find(
    (step) => step.name === "Retrieve the exact original release artifact",
  );
  assert.match(
    retrieval.run,
    new RegExp(`actions/artifacts/${recoveryPlan.incident.artifactId}/zip`),
  );
  assert.match(
    retrieval.run,
    new RegExp(recoveryPlan.incident.artifactZipSha256),
  );
  assert.match(
    retrieval.run,
    /target\/recovery-source\/original-release-artifact\.zip/,
  );
  assert.doesNotMatch(retrieval.run, /\bunzip\b/);
  const prepareCommand = prepare.steps.find((step) =>
    step.run?.includes("--mode prepare"),
  ).run;
  assert.match(
    prepareCommand,
    /--artifact-zip target\/recovery-source\/original-release-artifact\.zip/,
  );
  assert.match(
    prepareCommand,
    /--artifact-metadata target\/recovery-source\/original-artifact-metadata\.json/,
  );
  assert.match(prepareCommand, /--materialize-root target\/release-transfer/);
  const reverify = publish.steps.find(
    (step) => step.name === "Reverify the original candidate bytes",
  );
  assert.match(
    reverify.run,
    new RegExp(recoveryPlan.incident.artifactZipSha256),
  );
  assert.match(reverify.run, /release:verify-evidence/);
  const publishCommand = publish.steps.find((step) =>
    step.run?.includes("--mode publish"),
  ).run;
  assert.match(
    publishCommand,
    /--artifact-zip target\/release-transfer\/original-release-artifact\.zip/,
  );
  assert.match(
    publishCommand,
    /--artifact-metadata target\/release-transfer\/original-artifact-metadata\.json/,
  );
  assert.match(
    publishCommand,
    /--evidence target\/release-transfer\/candidate-evidence\.json/,
  );
  assert.match(publishCommand, /--archive-root target\/release-transfer/);
  assert(prepare.steps.some((step) => step.run?.includes("--mode prepare")));
  assert(publish.steps.some((step) => step.run?.includes("--mode publish")));
  assert.equal(
    [...prepare.steps, ...publish.steps].some((step) =>
      [
        "make release-transfer-create",
        "make release-transfer-validate",
      ].includes(step.run),
    ),
    false,
  );
  assert(
    verify.steps.some((step) => step.run?.includes("--recovery-evidence")),
  );
});

test("release workflow transfers one candidate to application tooling before publication", () => {
  const prepare = publishWorkflow.jobs["prepare-candidate"];
  const validate = publishWorkflow.jobs["validate-application-compatibility"];
  const publish = publishWorkflow.jobs["publish-bootstrap"];
  assert.equal(validate.needs, "prepare-candidate");
  assert.equal(publish.needs, "validate-application-compatibility");
  assert.equal(
    prepare.steps.find((step) => step.name === "Setup release Node.js").with[
      "node-version"
    ],
    "24.21.0",
  );
  assert.equal(
    validate.steps.find((step) => step.name === "Setup application Node.js")
      .with["node-version"],
    "22.13.0",
  );
  assert(
    prepare.steps.some((step) => step.run === "make release-transfer-create"),
  );
  assert(
    validate.steps.some(
      (step) => step.run === "make release-transfer-validate",
    ),
  );
  assert(
    publish.steps.some(
      (step) =>
        step.name === "Reverify exact candidate bytes before publication",
    ),
  );
  assert(
    publishWorkflow.jobs["verify-public-registry"].steps.some((step) =>
      step.run?.includes("npm run registry:verify"),
    ),
  );
  const registryVerifier = publishWorkflow.jobs["verify-public-registry"];
  assert.equal(
    registryVerifier.steps.find(
      (step) => step.name === "Setup application Node.js",
    ).with["node-version"],
    "22.13.0",
  );
  assert(
    registryVerifier.steps.some(
      (step) => step.run === "npm install --global npm@10.9.2",
    ),
  );
});

test("public-registry verification reuses the explicitly provisioned Chromium path", () => {
  const registryVerifier = publishWorkflow.jobs["verify-public-registry"];
  assert.equal(
    registryVerifier.env.PLAYWRIGHT_BROWSERS_PATH,
    "target/playwright",
  );
  const provisionIndex = registryVerifier.steps.findIndex(
    (step) =>
      step.name === "Provision Chromium" && step.run === "make browser-install",
  );
  const verifyIndex = registryVerifier.steps.findIndex(
    (step) =>
      step.name === "Verify exact public registry packages and provenance" &&
      step.run?.includes("npm run registry:verify"),
  );
  assert.notEqual(provisionIndex, -1);
  assert.notEqual(verifyIndex, -1);
  assert(provisionIndex < verifyIndex);
  const continuationVerifyIndex = registryVerifier.steps.findIndex(
    (step) =>
      step.name === "Verify existing public registry packages and provenance" &&
      step.run?.includes("npm run registry:verify"),
  );
  assert.notEqual(continuationVerifyIndex, -1);
  assert(provisionIndex < continuationVerifyIndex);
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

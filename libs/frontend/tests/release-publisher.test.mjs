import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import semver from "semver";

import { loadReleaseContract } from "../scripts/release-contract.mjs";
import { sha512Integrity } from "../scripts/release-evidence.mjs";
import {
  baselineDigest,
  loadCompatibilityLedger,
} from "../scripts/compatibility-baselines.mjs";
import {
  releasePolicyDigest,
  releaseRecordDigest,
  publishingAttemptModel,
  publishingTerminalModel,
  validateReleaseRecord,
} from "../scripts/release-record.mjs";
import {
  currentPublishingExecution,
  assertRetainedCandidateSelection,
  reviewedCoordinateHistoryStart,
  loadKnownPublishedCoordinates,
  assertNoKnownPublishedSelection,
  executeOrdinaryPublication as executePublisher,
  reconcileSelected,
  verifyPublishedMember,
} from "../scripts/release-publisher.mjs";
import {
  assertCompleteCandidateAttemptHistory,
  assertTerminalJobBoundary,
  verifyRetainedTerminal,
} from "../scripts/release-artifact.mjs";
import { run } from "../scripts/process.mjs";
import { releaseSummary } from "../scripts/release-summary.mjs";
import { signedPublishingProvenance } from "./helpers/signed-provenance.mjs";

const commit = "a".repeat(40);
const ref = {
  artifactId: 101,
  runId: "201",
  runAttempt: "1",
  sourceCommit: commit,
  zipSha256: "a".repeat(64),
  recordDigest: `sha256-${"A".repeat(43)}=`,
};
const signerIssuer = "https://token.actions.githubusercontent.com";

async function executeOrdinaryPublication(input) {
  return executePublisher({
    ...input,
    // Synthetic records use disposable package coordinates and readback fixtures.
    knownPublished: input.knownPublished ?? { packages: [] },
    verifyIntent: input.verifyIntent ?? (async () => {}),
  });
}

async function syntheticCandidate(ids, contract, root) {
  const ledger = await loadCompatibilityLedger();
  const archives = {};
  for (const id of ids) {
    const bytes = Buffer.from(`fixture-${id}`);
    const filename = `${id}.tgz`;
    await writeFile(path.join(root, filename), bytes);
    archives[id] = {
      filename,
      bytes: bytes.length,
      integrity: `sha512-${createHash("sha512").update(bytes).digest("base64")}`,
    };
  }
  const candidate = validateReleaseRecord({
    schemaVersion: 1,
    kind: "candidate",
    readiness: "complete",
    sourceCommit: commit,
    transferOrigin: null,
    selected: ids.map((id) => {
      const member = contract.inventory.members.find(
        (entry) => entry.id === id,
      );
      return {
        id,
        coordinate: `${contract.packages[id].name}@${contract.packages[id].version}`,
        builder: member.builder,
        validator: member.validator,
        consumer: member.consumer,
      };
    }),
    compatibilityOnly: [],
    policyDigest: releasePolicyDigest(contract),
    baselineDigest: `sha256-${baselineDigest(ledger)}`,
    expectedProvenance: contract.expectedProvenance,
    observedToolchains: {
      producer: contract.releaseToolchain,
      application: contract.applicationToolchain,
    },
    gates: { archives: { validated: true } },
    archives,
    manifestRanges: Object.fromEntries(
      ids.map((id) => [
        id,
        {
          dependencies:
            contract.packages[id].expectedManifest.dependencies ?? {},
          peerDependencies:
            contract.packages[id].expectedManifest.peerDependencies ?? {},
        },
      ]),
    ),
  });
  return {
    candidate,
    archivePaths: Object.fromEntries(
      ids.map((id) => [id, path.join(root, archives[id].filename)]),
    ),
  };
}

function attemptFor(
  candidate,
  contract,
  sourceCommit,
  runId,
  candidateRef = ref,
) {
  return publishingAttemptModel({
    candidate,
    candidateArtifact: candidateRef,
    execution: {
      repository: "ThalesGroup/fred",
      workflow: contract.workflowFilename,
      sourceCommit,
      runId,
      runAttempt: "1",
      signerIssuer,
    },
  });
}

test("actual GitHub execution identity is independent of candidate source", async () => {
  const contract = await loadReleaseContract(
    "release/proposed-release-contract.json",
  );
  const environment = {
    GITHUB_REPOSITORY: "ThalesGroup/fred",
    GITHUB_REF: "refs/heads/swift",
    GITHUB_WORKFLOW_REF: `ThalesGroup/fred/.github/workflows/${contract.workflowFilename}@refs/heads/swift`,
    GITHUB_SHA: "b".repeat(40),
    GITHUB_RUN_ID: "301",
    GITHUB_RUN_ATTEMPT: "2",
  };
  assert.equal(
    currentPublishingExecution(environment, contract).sourceCommit,
    "b".repeat(40),
  );
  assert.equal(
    currentPublishingExecution(environment, contract).runAttempt,
    "2",
  );
  assert.throws(
    () =>
      currentPublishingExecution(
        { ...environment, GITHUB_WORKFLOW_REF: "wrong" },
        contract,
      ),
    /workflow/,
  );
  assert.throws(
    () =>
      currentPublishingExecution(
        { ...environment, GITHUB_SHA: commit.slice(1) },
        contract,
      ),
    /commit/,
  );
});

async function assertSelectedVersionHistory(currentVersion) {
  const contract = await loadReleaseContract(
    "release/proposed-release-contract.json",
  );
  contract.packages.iframeSdk.version = currentVersion;
  const root = await mkdtemp(path.join(os.tmpdir(), "fred-version-history-"));
  try {
    const source = path.join(root, "source");
    const producer = path.join(source, "libs", "frontend");
    const changelog = path.join(producer, "iframe-sdk", "CHANGELOG.md");
    await mkdir(path.dirname(changelog), { recursive: true });
    await run("git", ["init", "-q", "-b", "swift", source]);
    const { name: packageName, version } = contract.packages.iframeSdk;
    const differentVersion = semver.inc(version, "prerelease", "alpha");
    assert(
      semver.valid(differentVersion),
      "derived fixture version is invalid",
    );
    assert.notEqual(differentVersion, version);
    await writeFile(
      changelog,
      `## ${version}\nReview: approved\nChanges: fixture\n`,
    );
    await run("git", ["add", "libs/frontend/iframe-sdk/CHANGELOG.md"], {
      cwd: source,
    });
    await run(
      "git",
      [
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-qm",
        "reviewed version",
      ],
      { cwd: source },
    );
    const { stdout: sourceCommit } = await run("git", ["rev-parse", "HEAD"], {
      cwd: source,
    });
    const { candidate } = await syntheticCandidate(
      ["iframeSdk"],
      contract,
      root,
    );
    const reviewed = validateReleaseRecord({
      ...candidate,
      sourceCommit: sourceCommit.trim(),
    });
    const observed = new Date(Date.now() - 60_000).toISOString();
    const mergeEvidence = {
      token: "controlled",
      fetchImpl: async () =>
        Response.json([
          {
            base: { ref: "swift" },
            merged_at: observed,
            merge_commit_sha: sourceCommit.trim(),
          },
        ]),
    };
    const start = await reviewedCoordinateHistoryStart(
      reviewed,
      contract,
      (command, args, options) =>
        run(command, args, { ...options, cwd: producer }),
      mergeEvidence,
    );
    assert.equal(start, observed);
    const shallow = path.join(root, "shallow");
    await run("git", [
      "clone",
      "-q",
      "--depth",
      "1",
      `file://${source}`,
      shallow,
    ]);
    const { stdout: shallowState } = await run(
      "git",
      ["rev-parse", "--is-shallow-repository"],
      { cwd: shallow },
    );
    assert.equal(shallowState.trim(), "true");
    await assert.rejects(
      reviewedCoordinateHistoryStart(
        reviewed,
        contract,
        (command, args, options) =>
          run(command, args, {
            ...options,
            cwd: path.join(shallow, "libs", "frontend"),
          }),
        mergeEvidence,
      ),
      /complete Git history/,
    );
    await assert.rejects(
      reviewedCoordinateHistoryStart(
        reviewed,
        contract,
        async (command, args, options) =>
          args[0] === "log"
            ? { stdout: "" }
            : run(command, args, { ...options, cwd: producer }),
        mergeEvidence,
      ),
      /no exact reviewed changelog introduction commit/,
    );
    await assert.rejects(
      reviewedCoordinateHistoryStart(
        validateReleaseRecord({
          ...reviewed,
          selected: reviewed.selected.map((member) => ({
            ...member,
            coordinate: `${packageName}@${differentVersion}`,
          })),
        }),
        contract,
        (command, args, options) =>
          run(command, args, { ...options, cwd: producer }),
        mergeEvidence,
      ),
      /differs from reviewed manifest/,
    );
    const futureContract = structuredClone(contract);
    futureContract.packages.iframeSdk.version = differentVersion;
    await writeFile(
      changelog,
      `## ${futureContract.packages.iframeSdk.version}\nReview: approved\nChanges: changed fixture\n\n## ${version}\nReview: approved\nChanges: fixture\n`,
    );
    await run("git", ["add", "libs/frontend/iframe-sdk/CHANGELOG.md"], {
      cwd: source,
    });
    await run(
      "git",
      [
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-qm",
        "next reviewed version",
      ],
      { cwd: source },
    );
    const { stdout: futureCommit } = await run("git", ["rev-parse", "HEAD"], {
      cwd: source,
    });
    const { candidate: futureCandidate } = await syntheticCandidate(
      ["iframeSdk"],
      futureContract,
      root,
    );
    const futureObserved = new Date(Date.now() - 30_000).toISOString();
    assert.equal(
      await reviewedCoordinateHistoryStart(
        validateReleaseRecord({
          ...futureCandidate,
          sourceCommit: futureCommit.trim(),
        }),
        futureContract,
        (command, args, options) =>
          run(command, args, { ...options, cwd: producer }),
        {
          token: "controlled",
          fetchImpl: async () =>
            Response.json([
              {
                base: { ref: "swift" },
                merged_at: futureObserved,
                merge_commit_sha: futureCommit.trim(),
              },
            ]),
        },
      ),
      futureObserved,
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
}

for (const currentVersion of ["0.1.0-alpha.1", "0.1.0-alpha.2"]) {
  test(`selected ${currentVersion} version history uses a disposable repository and rejects incomplete production history`, () =>
    assertSelectedVersionHistory(currentVersion));
}

test("reviewed version history ignores an earlier substring-colliding changelog heading", async () => {
  const contract = await loadReleaseContract(
    "release/proposed-release-contract.json",
  );
  const root = await mkdtemp(path.join(os.tmpdir(), "fred-heading-history-"));
  try {
    const producer = path.join(root, "libs", "frontend");
    const changelog = path.join(producer, "iframe-sdk", "CHANGELOG.md");
    const version = contract.packages.iframeSdk.version;
    const collisionVersion = `${version}0`;
    await mkdir(path.dirname(changelog), { recursive: true });
    await run("git", ["init", "-q"], { cwd: root });
    await writeFile(
      changelog,
      `## ${collisionVersion}\nReview: approved\nChanges: earlier fixture\n`,
    );
    await run("git", ["add", "libs/frontend/iframe-sdk/CHANGELOG.md"], {
      cwd: root,
    });
    await run(
      "git",
      [
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-qm",
        "earlier substring",
      ],
      { cwd: root },
    );
    await writeFile(
      changelog,
      `## ${version}\nReview: approved\nChanges: exact fixture\n\n## ${collisionVersion}\nReview: approved\nChanges: earlier fixture\n`,
    );
    await run("git", ["add", "libs/frontend/iframe-sdk/CHANGELOG.md"], {
      cwd: root,
    });
    await run(
      "git",
      [
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-qm",
        "exact heading",
      ],
      {
        cwd: root,
        env: {
          ...process.env,
          GIT_AUTHOR_DATE: new Date(Date.now() + 3_600_000).toISOString(),
          GIT_COMMITTER_DATE: new Date(Date.now() + 3_600_000).toISOString(),
        },
      },
    );
    const { stdout: sourceCommit } = await run("git", ["rev-parse", "HEAD"], {
      cwd: root,
    });
    const { candidate } = await syntheticCandidate(
      ["iframeSdk"],
      contract,
      root,
    );
    const observed = new Date(Date.now() - 30_000).toISOString();
    const history = await reviewedCoordinateHistoryStart(
      validateReleaseRecord({
        ...candidate,
        sourceCommit: sourceCommit.trim(),
      }),
      contract,
      (command, args, options) =>
        run(command, args, { ...options, cwd: producer }),
      {
        token: "controlled",
        fetchImpl: async () =>
          Response.json([
            {
              base: { ref: "swift" },
              merged_at: new Date(Date.now() - 60_000).toISOString(),
              merge_commit_sha: "f".repeat(40),
            },
            {
              base: { ref: "swift" },
              merged_at: observed,
              merge_commit_sha: sourceCommit.trim(),
            },
          ]),
      },
    );
    assert.equal(
      history,
      observed,
      "independently observed merge time must beat skewed future Git commit dates",
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("historically published alpha.1 versions never become absent candidates after a 404", async () => {
  const contract = await loadReleaseContract(
    "release/proposed-release-contract.json",
  );
  const ledger = await loadKnownPublishedCoordinates();
  assert.equal(ledger.historicalVerification.artifactId, 10365859307);
  assert.deepEqual(
    ledger.packages.map(({ coordinate }) => coordinate),
    [
      "@fred-oss/design-tokens@0.1.0-alpha.1",
      "@fred-oss/ui@0.1.0-alpha.1",
      "@fred-oss/iframe-sdk@0.1.0-alpha.1",
    ],
  );
  const historicalContract = structuredClone(contract);
  historicalContract.packages.iframeSdk.version = "0.1.0-alpha.1";
  const root = await mkdtemp(path.join(os.tmpdir(), "fred-known-published-"));
  try {
    const { candidate, archivePaths } = await syntheticCandidate(
      ["iframeSdk"],
      historicalContract,
      root,
    );
    const attempt = attemptFor(
      candidate,
      historicalContract,
      "b".repeat(40),
      "301",
    );
    let commands = 0;
    await assert.rejects(
      executeOrdinaryPublication({
        candidate,
        candidateRef: ref,
        attempt,
        attemptRef: { ...ref, recordDigest: releaseRecordDigest(attempt) },
        priorAttempts: [],
        contract: historicalContract,
        archivePaths,
        knownPublished: ledger,
        readExact: async () => null,
        wait: async () => {},
        publishCommand: async () => {
          commands++;
        },
      }),
      /already published by historical verified release evidence/,
    );
    assert.equal(commands, 0);
    assert.doesNotThrow(() =>
      assertNoKnownPublishedSelection(
        {
          selected: [
            {
              coordinate: `${contract.packages.iframeSdk.name}@${contract.packages.iframeSdk.version}`,
            },
          ],
        },
        ledger,
      ),
    );
    const corrupted = path.join(root, "corrupted.json");
    await writeFile(
      corrupted,
      JSON.stringify({
        ...ledger,
        packages: [{ ...ledger.packages[0], integrity: "truncated" }],
      }),
    );
    await assert.rejects(
      loadKnownPublishedCoordinates(corrupted),
      /schema|integrity/,
    );
    const omitted = path.join(root, "omitted.json");
    await writeFile(
      omitted,
      JSON.stringify({ ...ledger, packages: ledger.packages.slice(0, 1) }),
    );
    await assert.rejects(
      loadKnownPublishedCoordinates(omitted),
      /historical release appendix/,
    );
    const wrongRun = path.join(root, "wrong-run.json");
    await writeFile(
      wrongRun,
      JSON.stringify({
        ...ledger,
        historicalVerification: {
          ...ledger.historicalVerification,
          runId: "999",
        },
      }),
    );
    await assert.rejects(
      loadKnownPublishedCoordinates(wrongRun),
      /verification trace differs/,
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("retained selection and current policy must match before protected publication", async () => {
  const contract = await loadReleaseContract(
    "release/proposed-release-contract.json",
  );
  assert.throws(
    () =>
      assertRetainedCandidateSelection(
        { selectedIds: ["designTokens", "ui"] },
        contract,
        "iframeSdk",
      ),
    /manual selection differs/,
  );
  const root = await mkdtemp(path.join(os.tmpdir(), "fred-policy-drift-"));
  try {
    const { candidate, archivePaths } = await syntheticCandidate(
      ["iframeSdk"],
      contract,
      root,
    );
    const changedPolicy = { ...contract, distTag: "latest" };
    const attempt = attemptFor(candidate, contract, "b".repeat(40), "301");
    let commands = 0;
    await assert.rejects(
      executeOrdinaryPublication({
        candidate,
        candidateRef: ref,
        attempt,
        attemptRef: {
          ...ref,
          recordDigest: releaseRecordDigest(attempt),
        },
        priorAttempts: [],
        contract: changedPolicy,
        archivePaths,
        publishCommand: async () => {
          commands++;
        },
      }),
      /dist-tag differs|candidate policy differs/,
    );
    assert.equal(commands, 0);
    const validInput = {
      candidate,
      candidateRef: ref,
      attempt,
      attemptRef: { ...ref, recordDigest: releaseRecordDigest(attempt) },
      priorAttempts: [],
      contract,
      archivePaths,
      publishCommand: async () => {
        commands++;
      },
    };
    await assert.rejects(
      executePublisher(validInput),
      /requires retained per-package intent readback/,
    );
    await assert.rejects(
      executePublisher({ ...validInput, verifyIntent: async () => {} }),
      /requires the reviewed known-published ledger/,
    );
    assert.equal(commands, 0);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("operator summary separates original candidate, attempt and verifier identities", () => {
  const attemptRef = { ...ref, artifactId: 202, sourceCommit: "b".repeat(40) };
  const output = releaseSummary({
    operation: "verify",
    selected: ["iframeSdk"],
    candidateRef: ref,
    attemptRef,
    result: {
      gates: { sigstoreProvenance: true },
      verifierExecution: {
        sourceCommit: "c".repeat(40),
        runId: "301",
        runAttempt: "2",
      },
    },
  });
  assert(output.includes(`Candidate: run ${ref.runId}`));
  assert(output.includes(`Publishing attempt: run ${attemptRef.runId}`));
  assert(output.includes(`Verifier: ${"c".repeat(40)} / 301 / 2`));
});

test("lost prior outcome verifies existing tokens but does not infer that UI was never attempted", async () => {
  const contract = await loadReleaseContract(
    "release/proposed-release-contract.json",
  );
  const root = await mkdtemp(path.join(os.tmpdir(), "fred-publisher-test-"));
  try {
    const { candidate, archivePaths } = await syntheticCandidate(
      ["designTokens", "ui"],
      contract,
      root,
    );
    const old = attemptFor(candidate, contract, "b".repeat(40), "301");
    const current = attemptFor(candidate, contract, "c".repeat(40), "401");
    const currentRef = {
      ...ref,
      artifactId: 202,
      recordDigest: releaseRecordDigest(current),
    };
    const calls = [];
    await assert.rejects(
      executeOrdinaryPublication({
        candidate,
        candidateRef: ref,
        attempt: current,
        attemptRef: currentRef,
        priorAttempts: [{ record: old, ref: { ...ref, artifactId: 102 } }],
        contract,
        archivePaths,
        readExact: async ({ candidate: expected }) =>
          expected.coordinate.includes("design-tokens")
            ? {
                name: expected.coordinate.slice(
                  0,
                  expected.coordinate.lastIndexOf("@"),
                ),
                version: expected.coordinate.slice(
                  expected.coordinate.lastIndexOf("@") + 1,
                ),
                dist: { integrity: expected.integrity },
              }
            : null,
        verifyExisting: async ({ attempts }) => ({
          cryptographicallyVerified: true,
          identity: { sourceCommit: attempts[0].record.execution.sourceCommit },
        }),
        publishCommand: async (_command, args) => {
          calls.push(args);
        },
        wait: async () => {},
      }),
      /visibility is unresolved after a retained publishing attempt/,
    );
    assert.equal(calls.length, 0);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("completed retained terminal evidence permits UI after tokens published and UI never invoked", async () => {
  const contract = await loadReleaseContract(
    "release/proposed-release-contract.json",
  );
  const root = await mkdtemp(path.join(os.tmpdir(), "fred-terminal-repro-"));
  try {
    const { candidate, archivePaths } = await syntheticCandidate(
      ["designTokens", "ui"],
      contract,
      root,
    );
    const old = attemptFor(candidate, contract, "b".repeat(40), "301");
    const current = attemptFor(candidate, contract, "c".repeat(40), "401");
    const calls = [];
    const terminal = publishingTerminalModel({
      attempt: old,
      passedBoundaries: ["designTokens"],
      possiblyInvoked: ["designTokens"],
    });
    assertTerminalJobBoundary({
      run: { status: "completed", conclusion: "failure" },
      jobs: {
        total_count: 1,
        jobs: [
          {
            name: "publish",
            run_id: 301,
            head_sha: old.execution.sourceCommit,
            status: "completed",
            conclusion: "failure",
            steps: [
              {
                name: "Read back attempt and publish demonstrably absent archives",
                status: "completed",
                conclusion: "failure",
                number: 12,
              },
              {
                name: "Durably retain aborted publishing boundaries",
                status: "completed",
                conclusion: "success",
                number: 13,
              },
            ],
          },
        ],
      },
      terminal,
      attempt: old,
    });
    const result = await executeOrdinaryPublication({
      candidate,
      candidateRef: ref,
      attempt: current,
      attemptRef: {
        ...ref,
        artifactId: 202,
        recordDigest: releaseRecordDigest(current),
      },
      priorAttempts: [{ record: old, ref: { ...ref, artifactId: 102 } }],
      verifiedTerminals: [{ record: terminal, verifiedBoundary: true }],
      contract,
      archivePaths,
      readExact: async ({ candidate: expected }) =>
        expected.coordinate.includes("design-tokens") || calls.length
          ? {
              name: expected.coordinate.slice(
                0,
                expected.coordinate.lastIndexOf("@"),
              ),
              version: expected.coordinate.slice(
                expected.coordinate.lastIndexOf("@") + 1,
              ),
              dist: { integrity: expected.integrity },
            }
          : null,
      verifyExisting: async () => ({
        cryptographicallyVerified: true,
        identity: { sourceCommit: old.execution.sourceCommit },
      }),
      publishCommand: async (_command, args) => calls.push(args),
      wait: async () => {},
    });
    assert.equal(result.states.designTokens, "matching");
    assert.equal(result.states.ui, "published");
    assert.equal(calls.length, 1);
    assert(calls[0][1].endsWith("ui.tgz"));
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("retained terminal ZIP and exact completed GitHub attempt are required before continuation", async () => {
  const contract = await loadReleaseContract(
    "release/proposed-release-contract.json",
  );
  const root = await mkdtemp(path.join(os.tmpdir(), "fred-terminal-artifact-"));
  try {
    const { candidate } = await syntheticCandidate(
      ["designTokens", "ui"],
      contract,
      root,
    );
    const old = attemptFor(candidate, contract, "b".repeat(40), "301");
    const terminal = publishingTerminalModel({
      attempt: old,
      passedBoundaries: ["designTokens"],
      possiblyInvoked: ["designTokens"],
    });
    await writeFile(
      path.join(root, "publishing-terminal.json"),
      `${JSON.stringify(terminal)}\n`,
    );
    await run("zip", ["-q", "terminal.zip", "publishing-terminal.json"], {
      cwd: root,
    });
    const zip = await import("node:fs/promises").then(({ readFile }) =>
      readFile(path.join(root, "terminal.zip")),
    );
    const terminalRef = {
      ...ref,
      artifactId: 303,
      runId: "301",
      sourceCommit: old.execution.sourceCommit,
      recordDigest: releaseRecordDigest(terminal),
    };
    const attempt = {
      record: old,
      ref: {
        ...terminalRef,
        artifactId: 302,
        recordDigest: releaseRecordDigest(old),
      },
    };
    const jobs = {
      total_count: 1,
      jobs: [
        {
          name: "publish",
          run_id: 301,
          head_sha: old.execution.sourceCommit,
          status: "completed",
          conclusion: "failure",
          steps: [
            {
              name: "Read back attempt and publish demonstrably absent archives",
              status: "completed",
              conclusion: "failure",
              number: 12,
            },
            {
              name: "Durably retain aborted publishing boundaries",
              status: "completed",
              conclusion: "success",
              number: 13,
            },
          ],
        },
      ],
    };
    const artifact = {
      zip,
      metadata: {
        name: `frontend-packages-terminal-${old.execution.sourceCommit}-301-1`,
      },
      runMetadata: { status: "completed", conclusion: "failure" },
    };
    const verify = (options = {}) =>
      verifyRetainedTerminal({
        ref: terminalRef,
        artifact,
        attempt,
        candidateRef: ref,
        token: "controlled",
        fetchImpl: async () => Response.json(options.jobs ?? jobs),
      });
    const valid = await verify();
    assert.equal(valid.verifiedBoundary, true);
    await valid.cleanup();
    await assert.rejects(
      verify({
        jobs: { ...jobs, jobs: [{ ...jobs.jobs[0], status: "in_progress" }] },
      }),
      /job remains unresolved/,
    );
    assert.throws(
      () =>
        assertTerminalJobBoundary({
          run: { status: "completed", conclusion: "cancelled" },
          jobs,
          terminal,
          attempt: old,
        }),
      /failed completed publishing attempt/,
    );
    assert.throws(
      () =>
        assertTerminalJobBoundary({
          run: { status: "completed", conclusion: "success" },
          jobs,
          terminal,
          attempt: old,
        }),
      /failed completed publishing attempt/,
    );
    assert.throws(
      () =>
        assertTerminalJobBoundary({
          run: artifact.runMetadata,
          jobs: { ...jobs, jobs: [{ ...jobs.jobs[0], conclusion: "success" }] },
          terminal,
          attempt: old,
        }),
      /publishing job did not abort/,
    );
    assert.throws(
      () =>
        assertTerminalJobBoundary({
          run: artifact.runMetadata,
          jobs: {
            ...jobs,
            jobs: [
              {
                ...jobs.jobs[0],
                steps: [
                  ...jobs.jobs[0].steps,
                  {
                    name: "npm publish another archive",
                    number: 14,
                    status: "completed",
                    conclusion: "success",
                  },
                ],
              },
            ],
          },
          terminal,
          attempt: old,
        }),
      /later publication path exists/,
    );
    assert.throws(
      () =>
        assertTerminalJobBoundary({
          run: artifact.runMetadata,
          jobs,
          terminal: {
            ...terminal,
            passedBoundaries: ["ui"],
            neverInvoked: ["designTokens"],
          },
          attempt: old,
        }),
      /exact serialized selection/,
    );
    await assert.rejects(
      verify({
        jobs: {
          ...jobs,
          jobs: [
            {
              ...jobs.jobs[0],
              steps: jobs.jobs[0].steps.map((step) =>
                step.number === 13 ? { ...step, conclusion: "failure" } : step,
              ),
            },
          ],
        },
      }),
      /terminal upload was not successful/,
    );
    await assert.rejects(
      verifyRetainedTerminal({
        ref: { ...terminalRef, recordDigest: ref.recordDigest },
        artifact,
        attempt,
        candidateRef: ref,
        token: "controlled",
        fetchImpl: async () => Response.json(jobs),
      }),
      /terminal record digest differs/,
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("npm acceptance with lost outcome reconstructs tokens and continues only untouched UI", async () => {
  const contract = await loadReleaseContract(
    "release/proposed-release-contract.json",
  );
  const root = await mkdtemp(path.join(os.tmpdir(), "fred-lost-outcome-"));
  try {
    const { candidate, archivePaths } = await syntheticCandidate(
      ["designTokens", "ui"],
      contract,
      root,
    );
    const old = attemptFor(candidate, contract, "b".repeat(40), "301");
    const current = attemptFor(candidate, contract, "c".repeat(40), "401");
    const oldRef = {
      ...ref,
      artifactId: 302,
      runId: "301",
      sourceCommit: old.execution.sourceCommit,
      recordDigest: releaseRecordDigest(old),
    };
    const currentRef = {
      ...ref,
      artifactId: 402,
      runId: "401",
      sourceCommit: current.execution.sourceCommit,
      recordDigest: releaseRecordDigest(current),
    };
    const published = new Set();
    const commands = [];
    const readExact = async ({ candidate: expected }) =>
      published.has(expected.coordinate)
        ? {
            name: expected.coordinate.slice(
              0,
              expected.coordinate.lastIndexOf("@"),
            ),
            version: expected.coordinate.slice(
              expected.coordinate.lastIndexOf("@") + 1,
            ),
            dist: { integrity: expected.integrity },
          }
        : null;
    let terminal;
    await assert.rejects(
      executeOrdinaryPublication({
        candidate,
        candidateRef: ref,
        attempt: old,
        attemptRef: oldRef,
        priorAttempts: [],
        contract,
        archivePaths,
        readExact,
        wait: async () => {},
        verifyIntent: async ({ member }) =>
          assert.equal(member.id, "designTokens"),
        onTerminal: async (record) => {
          terminal = record;
        },
        publishCommand: async (_npm, args) => {
          commands.push(args[1]);
          published.add(candidate.selected[0].coordinate);
          throw new Error("process stopped after npm accepted publication");
        },
      }),
      /process stopped after npm accepted publication/,
    );
    assert.deepEqual(terminal.possiblyInvoked, ["designTokens"]);
    assert.deepEqual(terminal.neverInvoked, ["ui"]);
    assert.equal(commands.length, 1);
    const result = await executeOrdinaryPublication({
      candidate,
      candidateRef: ref,
      attempt: current,
      attemptRef: currentRef,
      priorAttempts: [{ record: old, ref: oldRef }],
      verifiedTerminals: [{ record: terminal, verifiedBoundary: true }],
      contract,
      archivePaths,
      readExact,
      wait: async () => {},
      verifyExisting: ({ member, expected, attempts }) =>
        verifyPublishedMember({
          member,
          expected,
          contract,
          attempts,
          resolvePackage: async () => ({
            archivePath: archivePaths[member.id],
            integrity: await sha512Integrity(archivePaths[member.id]),
          }),
          verifySignature: async () =>
            signedPublishingProvenance({
              artifactDigest: expected.integrity,
              repository: contract.expectedProvenance.repository,
              sourceCommit: attempts[0].record.execution.sourceCommit,
              workflow: contract.expectedProvenance.workflow,
              runId: attempts[0].record.execution.runId,
              runAttempt: attempts[0].record.execution.runAttempt,
              certificateIssuer: contract.expectedProvenance.certificateIssuer,
            }),
        }),
      verifyIntent: async ({ member }) => assert.equal(member.id, "ui"),
      publishCommand: async (_npm, args) => {
        commands.push(args[1]);
        published.add(candidate.selected[1].coordinate);
      },
    });
    assert.deepEqual(result.states, {
      designTokens: "matching",
      ui: "published",
    });
    assert.deepEqual(
      commands.map((value) => path.basename(value)),
      ["designTokens.tgz", "ui.tgz"],
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("publisher reconciliation distinguishes signed attempts at the same commit", async () => {
  const contract = await loadReleaseContract(
    "release/proposed-release-contract.json",
  );
  const root = await mkdtemp(path.join(os.tmpdir(), "fred-signed-publisher-"));
  try {
    const { candidate, archivePaths } = await syntheticCandidate(
      ["iframeSdk"],
      contract,
      root,
    );
    const first = attemptFor(candidate, contract, "b".repeat(40), "301");
    const second = attemptFor(candidate, contract, "b".repeat(40), "302");
    const member = candidate.selected[0];
    const expected = {
      coordinate: member.coordinate,
      integrity: candidate.archives[member.id].integrity,
    };
    const resolvePackage = async () => ({
      archivePath: archivePaths[member.id],
      integrity: await sha512Integrity(archivePaths[member.id]),
    });
    const verifySignature = (runId) =>
      signedPublishingProvenance({
        artifactDigest: expected.integrity,
        repository: contract.expectedProvenance.repository,
        sourceCommit: first.execution.sourceCommit,
        workflow: contract.expectedProvenance.workflow,
        runId,
        runAttempt: "1",
        certificateIssuer: contract.expectedProvenance.certificateIssuer,
      });
    const input = {
      member,
      expected,
      contract,
      attempts: [{ record: first }, { record: second }],
      resolvePackage,
      verifySignature: () => verifySignature("302"),
    };
    const matched = await verifyPublishedMember(input);
    assert.equal(matched.attempt.record.execution.runId, "302");
    await assert.rejects(
      verifyPublishedMember({
        ...input,
        verifySignature: () => verifySignature("303"),
      }),
      /does not match any retained actual publishing execution/,
    );
    await assert.rejects(
      verifyPublishedMember({
        ...input,
        attempts: [{ record: second }, { record: second }],
      }),
      /attribution is ambiguous/,
    );
    await writeFile(archivePaths[member.id], "altered packed bytes");
    await assert.rejects(
      verifyPublishedMember(input),
      /downloaded registry archive integrity differs/,
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("failed package-specific intent readback prevents npm invocation and records untouched selection", async () => {
  const contract = await loadReleaseContract(
    "release/proposed-release-contract.json",
  );
  const root = await mkdtemp(path.join(os.tmpdir(), "fred-intent-fail-"));
  try {
    const { candidate, archivePaths } = await syntheticCandidate(
      ["designTokens", "ui"],
      contract,
      root,
    );
    const attempt = attemptFor(candidate, contract, "b".repeat(40), "301");
    let commands = 0;
    let terminal;
    await assert.rejects(
      executeOrdinaryPublication({
        candidate,
        candidateRef: ref,
        attempt,
        attemptRef: { ...ref, recordDigest: releaseRecordDigest(attempt) },
        priorAttempts: [],
        contract,
        archivePaths,
        readExact: async () => null,
        wait: async () => {},
        verifyIntent: async () => {
          throw new Error("intent upload/readback failed");
        },
        onTerminal: async (record) => {
          terminal = record;
        },
        publishCommand: async () => {
          commands++;
        },
      }),
      /intent upload\/readback failed/,
    );
    assert.equal(commands, 0);
    assert.deepEqual(terminal.neverInvoked, ["designTokens", "ui"]);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("repository artifact enumeration rejects omitted, expired, and altered publishing histories", async () => {
  const contract = await loadReleaseContract(
    "release/proposed-release-contract.json",
  );
  const root = await mkdtemp(path.join(os.tmpdir(), "fred-attempt-history-"));
  try {
    const { candidate } = await syntheticCandidate(
      ["iframeSdk"],
      contract,
      root,
    );
    const old = attemptFor(candidate, contract, "b".repeat(40), "301");
    const current = attemptFor(candidate, contract, "c".repeat(40), "401");
    const unrelated = attemptFor(
      validateReleaseRecord({
        ...candidate,
        sourceCommit: "d".repeat(40),
        selected: candidate.selected.map((member) => ({
          ...member,
          coordinate: `${contract.packages.iframeSdk.name}@${semver.inc(contract.packages.iframeSdk.version, "prerelease", "alpha")}`,
        })),
      }),
      contract,
      "e".repeat(40),
      "501",
    );
    const candidateMetadata = { created_at: "2026-09-15T01:00:00Z" };
    const candidateRunMetadata = {
      id: 201,
      created_at: "2026-09-15T00:00:00Z",
    };
    const entries = [];
    for (const [index, record] of [old, current, unrelated].entries()) {
      const dir = path.join(root, String(index));
      await import("node:fs/promises").then(({ mkdir }) => mkdir(dir));
      await writeFile(
        path.join(dir, "publishing-attempt.json"),
        `${JSON.stringify(record)}\n`,
      );
      await run("zip", ["-q", "attempt.zip", "publishing-attempt.json"], {
        cwd: dir,
      });
      const zip = await import("node:fs/promises").then(({ readFile }) =>
        readFile(path.join(dir, "attempt.zip")),
      );
      entries.push({
        zip,
        metadata: {
          id: 302 + index,
          name: `frontend-packages-attempt-${record.execution.sourceCommit}-${record.execution.runId}-1`,
          created_at:
            index === 2 ? "2026-09-15T00:30:00Z" : "2026-09-15T02:00:00Z",
          expired: false,
          digest: `sha256:${createHash("sha256").update(zip).digest("hex")}`,
          workflow_run: {
            id: Number(record.execution.runId),
            head_sha: record.execution.sourceCommit,
          },
        },
      });
    }
    const workflowRuns = [201, 301, 401, 501].map((id) => ({
      id,
      run_attempt: 1,
      head_branch: "swift",
      event: "workflow_dispatch",
      created_at: id === 501 ? "2026-09-15T00:30:00Z" : "2026-09-15T00:00:00Z",
    }));
    const fetchImpl = async (url) => {
      const archive = entries.find(({ metadata }) =>
        url.endsWith(`/artifacts/${metadata.id}/zip`),
      );
      if (archive) return new Response(archive.zip);
      if (url.includes("/workflows/Publish-frontend-packages.yml/runs?")) {
        assert.equal(
          new URL(url).searchParams.get("created"),
          ">=2026-09-14T12:00:00.000Z",
          "history must cover prior attempts against the same coordinate",
        );
        const included = workflowRuns.filter(
          ({ created_at }) =>
            Date.parse(created_at) >= Date.parse("2026-09-14T12:00:00Z"),
        );
        return Response.json({
          total_count: included.length,
          workflow_runs: included,
        });
      }
      if (url.includes("/attempts/") && url.includes("/jobs?")) {
        const runId = Number(url.match(/\/runs\/(\d+)\/attempts\//)?.[1]);
        if (runId === 201) return Response.json({ total_count: 0, jobs: [] });
        return Response.json({
          total_count: 1,
          jobs: [
            {
              name: "publish",
              status: runId === 401 ? "in_progress" : "completed",
              steps: [
                {
                  name: "Durably retain pre-command attempt",
                  status: "completed",
                  conclusion: "success",
                },
                {
                  name: "Read back attempt and publish demonstrably absent archives",
                  status: runId === 401 ? "in_progress" : "completed",
                  conclusion: runId === 401 ? null : "failure",
                },
              ],
            },
          ],
        });
      }
      return Response.json({
        total_count: entries.length,
        artifacts: entries.map(({ metadata }) => metadata),
      });
    };
    const input = {
      candidate,
      candidateRef: ref,
      candidateMetadata,
      candidateRunMetadata,
      historyLowerBound: "2026-09-14T12:00:00Z",
      currentRef: { artifactId: 303, runId: "401", runAttempt: "1" },
      priorRefs: [{ artifactId: 302, runId: "301", runAttempt: "1" }],
      token: "controlled",
      fetchImpl,
    };
    assert.deepEqual(
      await assertCompleteCandidateAttemptHistory(input),
      [302, 303],
    );
    const otherSameCoordinate = attemptFor(
      validateReleaseRecord({ ...candidate, sourceCommit: "d".repeat(40) }),
      contract,
      "e".repeat(40),
      "501",
    );
    const priorZip = entries[2].zip;
    await writeFile(
      path.join(root, "2", "publishing-attempt.json"),
      `${JSON.stringify(otherSameCoordinate)}\n`,
    );
    await run("zip", ["-q", "same.zip", "publishing-attempt.json"], {
      cwd: path.join(root, "2"),
    });
    entries[2].zip = await import("node:fs/promises").then(({ readFile }) =>
      readFile(path.join(root, "2", "same.zip")),
    );
    entries[2].metadata.digest = `sha256:${createHash("sha256").update(entries[2].zip).digest("hex")}`;
    await assert.rejects(
      assertCompleteCandidateAttemptHistory(input),
      /another retained candidate/,
    );
    entries[2].zip = priorZip;
    entries[2].metadata.digest = `sha256:${createHash("sha256").update(priorZip).digest("hex")}`;
    await assert.rejects(
      assertCompleteCandidateAttemptHistory({ ...input, priorRefs: [] }),
      /omit or add/,
    );
    entries[0].metadata.expired = true;
    await assert.rejects(
      assertCompleteCandidateAttemptHistory(input),
      /expired/,
    );
    entries[0].metadata.expired = false;
    entries[0].metadata.digest = `sha256:${"0".repeat(64)}`;
    await assert.rejects(
      assertCompleteCandidateAttemptHistory(input),
      /ZIP differs/,
    );
    entries[0].metadata.digest = `sha256:${createHash("sha256").update(entries[0].zip).digest("hex")}`;
    const missing = entries.shift();
    await assert.rejects(
      assertCompleteCandidateAttemptHistory({ ...input, priorRefs: [] }),
      /crossed an attempt boundary without its retained artifact/,
    );
    entries.unshift(missing);
    workflowRuns[1].run_attempt = 2;
    await assert.rejects(
      assertCompleteCandidateAttemptHistory(input),
      /crossed an attempt boundary without its retained artifact/,
    );
    workflowRuns[1].run_attempt = 1;
    const cappedFetch = async (url) =>
      url.includes("/workflows/Publish-frontend-packages.yml/runs?")
        ? Response.json({ total_count: 1000, workflow_runs: workflowRuns })
        : fetchImpl(url);
    await assert.rejects(
      assertCompleteCandidateAttemptHistory({
        ...input,
        fetchImpl: cappedFetch,
      }),
      /1000-run cap/,
    );
    entries[2].metadata.created_at = "2026-09-14T11:00:00Z";
    entries[2].metadata.expired = true;
    workflowRuns[3].created_at = "2026-09-14T10:00:00Z";
    assert.deepEqual(
      await assertCompleteCandidateAttemptHistory(input),
      [302, 303],
      "older unrelated attempts are outside this version's reviewed history window",
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("unresolved existing identity, mismatched bytes and visibility errors block publication", async () => {
  const contract = await loadReleaseContract(
    "release/proposed-release-contract.json",
  );
  const root = await mkdtemp(path.join(os.tmpdir(), "fred-publisher-test-"));
  try {
    const { candidate, archivePaths } = await syntheticCandidate(
      ["iframeSdk"],
      contract,
      root,
    );
    const attempt = attemptFor(candidate, contract, "c".repeat(40), "401");
    const attemptRef = {
      ...ref,
      artifactId: 202,
      recordDigest: releaseRecordDigest(attempt),
    };
    const readExact = async () => ({
      name: contract.packages.iframeSdk.name,
      version: contract.packages.iframeSdk.version,
    });
    let commands = 0;
    await assert.rejects(
      executeOrdinaryPublication({
        candidate,
        candidateRef: ref,
        attempt,
        attemptRef,
        priorAttempts: [],
        contract,
        archivePaths,
        readExact,
        publishCommand: async () => {
          commands++;
        },
        wait: async () => {},
      }),
      /without a retained outcome or pre-command attempt/,
    );
    await assert.rejects(
      executeOrdinaryPublication({
        candidate,
        candidateRef: ref,
        attempt,
        attemptRef,
        priorAttempts: [{ record: attempt }],
        contract,
        archivePaths,
        readExact,
        verifyExisting: async () => ({ cryptographicallyVerified: false }),
        publishCommand: async () => {
          commands++;
        },
        wait: async () => {},
      }),
      /lacks matching cryptographic provenance/,
    );
    assert.equal(commands, 0);
    await writeFile(archivePaths.iframeSdk, "altered");
    await assert.rejects(
      executeOrdinaryPublication({
        candidate,
        candidateRef: ref,
        attempt,
        attemptRef,
        priorAttempts: [],
        contract,
        archivePaths,
        readExact: async () => null,
        publishCommand: async () => {
          commands++;
        },
        wait: async () => {},
      }),
      /exact archive bytes differ/,
    );
    assert.equal(commands, 0);
    await assert.rejects(
      reconcileSelected({
        candidate,
        registry: contract.registry,
        readExact: async () => {
          throw new Error("registry unauthorized");
        },
        wait: async () => {},
      }),
      /unauthorized/,
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("failed attempt binding, OIDC rejection, and failed token verification never advance UI", async () => {
  const contract = await loadReleaseContract(
    "release/proposed-release-contract.json",
  );
  const root = await mkdtemp(path.join(os.tmpdir(), "fred-publisher-order-"));
  try {
    const { candidate, archivePaths } = await syntheticCandidate(
      ["designTokens", "ui"],
      contract,
      root,
    );
    const attempt = attemptFor(candidate, contract, "b".repeat(40), "501");
    const attemptRef = {
      ...ref,
      artifactId: 202,
      recordDigest: releaseRecordDigest(attempt),
    };
    let published = [];
    const base = {
      candidate,
      candidateRef: ref,
      attempt,
      attemptRef,
      priorAttempts: [],
      contract,
      archivePaths,
      readExact: async ({ candidate: expected }) =>
        published.length
          ? {
              name: expected.coordinate.slice(
                0,
                expected.coordinate.lastIndexOf("@"),
              ),
              version: expected.coordinate.slice(
                expected.coordinate.lastIndexOf("@") + 1,
              ),
              dist: { integrity: expected.integrity },
            }
          : null,
      wait: async () => {},
    };
    await assert.rejects(
      executeOrdinaryPublication({
        ...base,
        attemptRef: { ...attemptRef, recordDigest: ref.recordDigest },
        publishCommand: async () => {
          published.push("unexpected");
        },
      }),
      /attempt readback digest differs/,
    );
    assert.deepEqual(published, []);
    await assert.rejects(
      executeOrdinaryPublication({
        ...base,
        publishCommand: async (_command, args) => {
          published.push(args[1]);
          throw new Error("OIDC authorization rejected");
        },
      }),
      /OIDC authorization rejected/,
    );
    assert.equal(published.length, 1);
    assert(published[0].endsWith("designTokens.tgz"));
    published = [];
    await assert.rejects(
      executeOrdinaryPublication({
        ...base,
        publishCommand: async (_command, args) => {
          published.push(args[1]);
        },
        verifyExisting: async () => {
          throw new Error("token provenance rejected");
        },
      }),
      /token provenance rejected/,
    );
    assert.equal(published.length, 1);
    assert(published[0].endsWith("designTokens.tgz"));
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("SDK-only publication remains independent and registry 404 reads are bounded", async () => {
  const contract = await loadReleaseContract(
    "release/proposed-release-contract.json",
  );
  const root = await mkdtemp(path.join(os.tmpdir(), "fred-publisher-sdk-"));
  try {
    const { candidate, archivePaths } = await syntheticCandidate(
      ["iframeSdk"],
      contract,
      root,
    );
    const attempt = attemptFor(candidate, contract, "b".repeat(40), "501");
    const attemptRef = {
      ...ref,
      artifactId: 202,
      recordDigest: releaseRecordDigest(attempt),
    };
    let reads = 0;
    let published = false;
    const result = await executeOrdinaryPublication({
      candidate,
      candidateRef: ref,
      attempt,
      attemptRef,
      priorAttempts: [],
      contract,
      archivePaths,
      readExact: async ({ candidate: expected }) => {
        reads++;
        return published
          ? {
              name: contract.packages.iframeSdk.name,
              version: contract.packages.iframeSdk.version,
              dist: { integrity: expected.integrity },
            }
          : null;
      },
      publishCommand: async (_command, args, options) => {
        assert(args[1].endsWith("iframeSdk.tgz"));
        const { stdout: userConfig } = await run(
          "npm",
          ["config", "get", "userconfig"],
          {
            cwd: root,
            env: options.env,
          },
        );
        const { stdout: globalConfig } = await run(
          "npm",
          ["config", "get", "globalconfig"],
          {
            cwd: root,
            env: options.env,
          },
        );
        assert.equal(userConfig.trim(), options.env.NPM_CONFIG_USERCONFIG);
        assert.equal(globalConfig.trim(), options.env.NPM_CONFIG_GLOBALCONFIG);
        assert.notEqual(userConfig.trim(), globalConfig.trim());
        assert.equal(await readFile(userConfig.trim(), "utf8"), "");
        assert.equal(await readFile(globalConfig.trim(), "utf8"), "");
        published = true;
      },
      verifyExisting: async () => ({
        cryptographicallyVerified: true,
        identity: { sourceCommit: attempt.execution.sourceCommit },
      }),
      wait: async () => {},
    });
    assert.deepEqual(Object.keys(result.states), ["iframeSdk"]);
    assert.equal(result.states.iframeSdk, "published");
    assert(
      reads >= 7 && reads <= 8,
      "preflight plus post-command reads should be bounded",
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("registry visibility retries reads only and never infer matching identity from an attempt", async () => {
  const contract = await loadReleaseContract(
    "release/proposed-release-contract.json",
  );
  const root = await mkdtemp(
    path.join(os.tmpdir(), "fred-publisher-visibility-"),
  );
  try {
    const { candidate } = await syntheticCandidate(
      ["iframeSdk"],
      contract,
      root,
    );
    const attempt = attemptFor(candidate, contract, "b".repeat(40), "501");
    let reads = 0;
    const matched = await reconcileSelected({
      candidate,
      registry: contract.registry,
      priorAttempts: [{ record: attempt }],
      visibilityAttempts: 4,
      readExact: async () =>
        ++reads < 3
          ? null
          : {
              name: contract.packages.iframeSdk.name,
              version: contract.packages.iframeSdk.version,
              dist: { integrity: candidate.archives.iframeSdk.integrity },
            },
      verifyExisting: async () => ({ cryptographicallyVerified: true }),
      wait: async () => {},
    });
    assert.equal(reads, 3);
    assert.equal(matched.iframeSdk, "matching");
    reads = 0;
    await assert.rejects(
      reconcileSelected({
        candidate,
        registry: contract.registry,
        priorAttempts: [{ record: attempt }],
        visibilityAttempts: 4,
        readExact: async () => {
          reads++;
          return { name: contract.packages.iframeSdk.name };
        },
        verifyExisting: async () => ({ cryptographicallyVerified: false }),
        wait: async () => {},
      }),
      /lacks matching cryptographic provenance/,
    );
    assert.equal(reads, 1, "unsafe metadata does not get visibility retries");
    reads = 0;
    const absent = await reconcileSelected({
      candidate,
      registry: contract.registry,
      visibilityAttempts: 4,
      readExact: async () => {
        reads++;
        return null;
      },
      wait: async () => {},
    });
    assert.equal(reads, 4);
    assert.equal(absent.iframeSdk, "absent");
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("exhausted 404 reads after a prior publishing attempt never repeat publication", async () => {
  const contract = await loadReleaseContract(
    "release/proposed-release-contract.json",
  );
  const root = await mkdtemp(path.join(os.tmpdir(), "fred-prior-404-"));
  try {
    const { candidate, archivePaths } = await syntheticCandidate(
      ["iframeSdk"],
      contract,
      root,
    );
    const prior = attemptFor(candidate, contract, "b".repeat(40), "301");
    const current = attemptFor(candidate, contract, "c".repeat(40), "401");
    let commands = 0;
    let reads = 0;
    await assert.rejects(
      executeOrdinaryPublication({
        candidate,
        candidateRef: ref,
        attempt: current,
        attemptRef: {
          ...ref,
          artifactId: 202,
          recordDigest: releaseRecordDigest(current),
        },
        priorAttempts: [{ record: prior }],
        contract,
        archivePaths,
        readExact: async () => {
          reads++;
          return null;
        },
        publishCommand: async () => {
          commands++;
        },
        wait: async () => {},
      }),
      /unresolved|visibility/i,
    );
    assert.equal(reads, 6);
    assert.equal(commands, 0);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

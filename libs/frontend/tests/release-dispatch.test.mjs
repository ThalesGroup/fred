import assert from "node:assert/strict";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { loadReleaseContract } from "../scripts/release-contract.mjs";
import { validateDispatch } from "../scripts/release-dispatch.mjs";
import { run } from "../scripts/process.mjs";

const script = fileURLToPath(
  new URL("../scripts/release-dispatch.mjs", import.meta.url),
);
const ref = {
  artifactId: 123,
  runId: "456",
  runAttempt: "1",
  sourceCommit: "a".repeat(40),
  zipSha256: "a".repeat(64),
  recordDigest: `sha256-${"A".repeat(43)}=`,
};

test("manual operations share selected-package parsing and reject invalid evidence", async () => {
  const contract = await loadReleaseContract(
    "release/proposed-release-contract.json",
  );
  const input = {
    operation: "prepare-only",
    selection: "iframeSdk",
    candidateRef: "",
    attemptRefs: "[]",
    contract,
  };
  assert.deepEqual(validateDispatch(input).selectedIds, ["iframeSdk"]);
  assert.equal(validateDispatch(input).fresh, true);
  assert.deepEqual(
    validateDispatch({
      ...input,
      operation: "publish",
      candidateRef: JSON.stringify(ref),
      attemptRefs: JSON.stringify([ref]),
    }).attempts,
    [ref],
  );
  assert.equal(
    validateDispatch({
      ...input,
      operation: "verify",
      candidateRef: JSON.stringify(ref),
      attemptRefs: JSON.stringify([ref]),
    }).fresh,
    false,
  );
  const terminalRef = { ...ref, artifactId: ref.artifactId + 1 };
  assert.deepEqual(
    validateDispatch({
      ...input,
      operation: "publish",
      candidateRef: JSON.stringify(ref),
      attemptRefs: JSON.stringify([ref]),
      terminalRefs: JSON.stringify([terminalRef]),
    }).terminals,
    [terminalRef],
  );
  for (const mutation of [
    { operation: "publish-bootstrap" },
    { selection: "" },
    { selection: "iframeSdk,iframeSdk" },
    { selection: "private-root" },
    { selection: "ui," },
    { candidateRef: "{" },
    { operation: "verify" },
    { operation: "prepare-only", candidateRef: JSON.stringify(ref) },
    { operation: "publish", attemptRefs: JSON.stringify([ref]) },
    { terminalRefs: JSON.stringify([terminalRef]) },
    {
      operation: "publish",
      candidateRef: JSON.stringify(ref),
      terminalRefs: JSON.stringify([terminalRef]),
    },
    {
      operation: "publish",
      candidateRef: JSON.stringify(ref),
      attemptRefs: JSON.stringify([ref]),
      terminalRefs: JSON.stringify([terminalRef, terminalRef]),
    },
    {
      operation: "publish",
      candidateRef: JSON.stringify(ref),
      attemptRefs: JSON.stringify([ref]),
      terminalRefs: JSON.stringify([{ ...terminalRef, runId: "999" }]),
    },
    {
      operation: "verify",
      candidateRef: JSON.stringify(ref),
      attemptRefs: "[]",
    },
    {
      operation: "verify",
      candidateRef: JSON.stringify({ ...ref, zipSha256: "bad" }),
      attemptRefs: JSON.stringify([ref]),
    },
    {
      operation: "verify",
      candidateRef: JSON.stringify(ref),
      attemptRefs: JSON.stringify([ref, ref]),
    },
  ])
    assert.throws(() => validateDispatch({ ...input, ...mutation }));
});

test("the actual input CLI rejects wrong branch in a fresh process", async () => {
  await assert.rejects(
    run("node", [script], {
      cwd: fileURLToPath(new URL("..", import.meta.url)),
      env: {
        ...process.env,
        RELEASE_OPERATION: "prepare-only",
        RELEASE_SELECTION: "iframeSdk",
        RELEASE_ATTEMPT_REFS: "[]",
        GITHUB_REF: "refs/heads/feature",
        GITHUB_REPOSITORY: "ThalesGroup/fred",
      },
    }),
    /release dispatch requires swift/,
  );
  const { stdout } = await run("node", [script], {
    cwd: fileURLToPath(new URL("..", import.meta.url)),
    env: {
      ...process.env,
      RELEASE_OPERATION: "prepare-only",
      RELEASE_SELECTION: "iframeSdk",
      RELEASE_ATTEMPT_REFS: "[]",
      GITHUB_REF: "refs/heads/swift",
      GITHUB_REPOSITORY: "ThalesGroup/fred",
    },
  });
  assert.deepEqual(JSON.parse(stdout).selectedIds, ["iframeSdk"]);
});

test("failed-job publish reruns reject fresh candidate creation without pinned prior evidence", async () => {
  const contract = await loadReleaseContract(
    "release/proposed-release-contract.json",
  );
  const input = {
    operation: "publish",
    selection: "iframeSdk",
    candidateRef: "",
    attemptRefs: "[]",
    contract,
    runAttempt: "2",
  };
  assert.throws(() => validateDispatch(input), /failed-job publishing rerun/);
  assert.throws(
    () => validateDispatch({ ...input, candidateRef: JSON.stringify(ref) }),
    /failed-job publishing rerun/,
  );
  assert.equal(
    validateDispatch({
      ...input,
      candidateRef: JSON.stringify(ref),
      attemptRefs: JSON.stringify([ref]),
    }).fresh,
    false,
  );
  await assert.rejects(
    run("node", [script], {
      cwd: fileURLToPath(new URL("..", import.meta.url)),
      env: {
        ...process.env,
        RELEASE_OPERATION: "publish",
        RELEASE_SELECTION: "iframeSdk",
        RELEASE_CANDIDATE_REF: "",
        RELEASE_ATTEMPT_REFS: "[]",
        GITHUB_REF: "refs/heads/swift",
        GITHUB_REPOSITORY: "ThalesGroup/fred",
        GITHUB_RUN_ATTEMPT: "2",
      },
    }),
    /failed-job publishing rerun/,
  );
});

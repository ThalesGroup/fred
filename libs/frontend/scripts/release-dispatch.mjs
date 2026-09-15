import assert from "node:assert/strict";
import { appendFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

import { loadReleaseContract } from "./release-contract.mjs";
import { selectReleaseMembers } from "./release-selection.mjs";

const sha256 = /^[a-f0-9]{64}$/;
const recordDigest = /^sha256-[A-Za-z0-9+/]{43}=$/;

export function validateArtifactRef(value, label = "artifact") {
  assert(
    value && typeof value === "object" && !Array.isArray(value),
    `${label} must be an object`,
  );
  assert.deepEqual(
    Object.keys(value).sort(),
    [
      "artifactId",
      "recordDigest",
      "runAttempt",
      "runId",
      "sourceCommit",
      "zipSha256",
    ].sort(),
    `${label} fields differ`,
  );
  assert(
    Number.isSafeInteger(value.artifactId) && value.artifactId > 0,
    `${label} ID invalid`,
  );
  assert(/^[1-9]\d*$/.test(String(value.runId)), `${label} run ID invalid`);
  assert(
    /^[1-9]\d*$/.test(String(value.runAttempt)),
    `${label} run attempt invalid`,
  );
  assert(sha256.test(value.zipSha256), `${label} ZIP SHA-256 invalid`);
  assert(
    recordDigest.test(value.recordDigest),
    `${label} record digest invalid`,
  );
  assert(
    /^[a-f0-9]{40}$/.test(value.sourceCommit),
    `${label} source commit invalid`,
  );
  return value;
}

function parseJsonInput(value, label) {
  if (!value?.trim()) return undefined;
  try {
    return JSON.parse(value);
  } catch {
    throw new Error(`${label} must be valid JSON`);
  }
}

export function validateDispatch({
  operation,
  selection,
  candidateRef,
  attemptRefs,
  terminalRefs,
  contract,
  runAttempt = "1",
}) {
  assert(
    ["prepare-only", "publish", "verify"].includes(operation),
    `unsupported release operation ${operation}`,
  );
  const selectedIds = selectReleaseMembers(contract, selection);
  const candidate = parseJsonInput(candidateRef, "candidate reference");
  const attempts = parseJsonInput(attemptRefs, "attempt references") ?? [];
  const terminals = parseJsonInput(terminalRefs, "terminal references") ?? [];
  if (candidate) validateArtifactRef(candidate, "candidate reference");
  assert(Array.isArray(attempts), "attempt references must be a JSON array");
  assert(Array.isArray(terminals), "terminal references must be a JSON array");
  attempts.forEach((ref, index) =>
    validateArtifactRef(ref, `attempt reference ${index}`),
  );
  terminals.forEach((ref, index) =>
    validateArtifactRef(ref, `terminal reference ${index}`),
  );
  assert.equal(
    new Set(terminals.map(({ artifactId }) => artifactId)).size,
    terminals.length,
    "duplicate terminal artifact",
  );
  assert(
    terminals.every((terminal) =>
      attempts.some(
        (attempt) =>
          attempt.runId === terminal.runId &&
          attempt.runAttempt === terminal.runAttempt &&
          attempt.sourceCommit === terminal.sourceCommit,
      ),
    ),
    "terminal reference has no matching attempt reference",
  );
  assert.equal(
    new Set(attempts.map(({ artifactId }) => artifactId)).size,
    attempts.length,
    "duplicate attempt artifact",
  );
  if (operation === "prepare-only") {
    assert(
      !candidate && attempts.length === 0 && terminals.length === 0,
      "preparation does not accept retained publication evidence",
    );
  } else if (operation === "verify") {
    assert(
      candidate,
      "verification requires an explicit candidate artifact reference",
    );
    assert(
      attempts.length > 0,
      "verification requires retained publishing attempts",
    );
  } else if (!candidate) {
    assert(
      attempts.length === 0 && terminals.length === 0,
      "fresh publication cannot reference old attempts without a candidate",
    );
  }
  if (operation === "publish" && Number(runAttempt) > 1)
    assert(
      candidate && attempts.length > 0,
      "a failed-job publishing rerun requires the original candidate and retained prior attempt references; fresh publication is unsafe",
    );
  return {
    operation,
    selectedIds,
    candidate,
    attempts,
    terminals,
    fresh: operation !== "verify" && !candidate,
  };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const contract = await loadReleaseContract(
    "release/proposed-release-contract.json",
  );
  const result = validateDispatch({
    operation: process.env.RELEASE_OPERATION ?? "prepare-only",
    selection:
      process.env.RELEASE_SELECTION === undefined
        ? undefined
        : process.env.RELEASE_SELECTION,
    candidateRef: process.env.RELEASE_CANDIDATE_REF,
    attemptRefs: process.env.RELEASE_ATTEMPT_REFS,
    terminalRefs: process.env.RELEASE_TERMINAL_REFS,
    contract,
    runAttempt: process.env.GITHUB_RUN_ATTEMPT,
  });
  assert.equal(
    process.env.GITHUB_REF,
    `refs/heads/${contract.sourceBranch}`,
    "release dispatch requires swift",
  );
  assert.equal(
    process.env.GITHUB_REPOSITORY,
    "ThalesGroup/fred",
    "release repository differs from policy",
  );
  const output = process.env.GITHUB_OUTPUT;
  if (output)
    await appendFile(
      output,
      [
        `operation=${result.operation}`,
        `selected=${result.selectedIds.join(",")}`,
        `fresh=${result.fresh}`,
        `candidate_ref=${JSON.stringify(result.candidate ?? {})}`,
        `candidate_source=${result.candidate?.sourceCommit ?? ""}`,
        `attempt_refs=${JSON.stringify(result.attempts)}`,
        `terminal_refs=${JSON.stringify(result.terminals)}`,
      ].join("\n") + "\n",
    );
  process.stdout.write(
    JSON.stringify({
      operation: result.operation,
      selectedIds: result.selectedIds,
      fresh: result.fresh,
    }) + "\n",
  );
}

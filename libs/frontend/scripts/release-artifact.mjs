import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import {
  appendFile,
  lstat,
  mkdtemp,
  readFile,
  readdir,
  rm,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { loadCompatibilityLedger } from "./compatibility-baselines.mjs";
import { validateFixtureTransferMetadata } from "./fixture-transfer.mjs";
import {
  verifyCandidateEvidence,
  sha512Integrity,
} from "./release-evidence.mjs";
import {
  candidateRecordFromEvidence,
  releaseRecordDigest,
  validateReleaseRecord,
} from "./release-record.mjs";
import { validateArtifactRef } from "./release-dispatch.mjs";
import { run } from "./process.mjs";

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

// Earliest committed version of this retained workflow (5032a83e, 2026-09-14 12:30:27 +02:00).
// A selected version's reviewed changelog introduction supplies the narrower history boundary.
const publishingWorkflowEpoch = Date.parse("2026-09-14T10:30:27.000Z");

export async function retrieveReleaseArtifact({
  ref,
  repository,
  token,
  fetchImpl = fetch,
}) {
  validateArtifactRef(ref);
  assert(
    repository === "ThalesGroup/fred",
    "artifact repository must match release policy",
  );
  assert(token, "GITHUB_TOKEN is required for read-only artifact retrieval");
  const endpoint = `https://api.github.com/repos/${repository}/actions/artifacts/${ref.artifactId}`;
  const headers = {
    Authorization: `Bearer ${token}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
  };
  const metadataResponse = await fetchImpl(endpoint, { headers });
  assert(
    metadataResponse.ok,
    `artifact ${ref.artifactId} API lookup failed (${metadataResponse.status}); it may be expired or inaccessible`,
  );
  const metadata = await metadataResponse.json();
  assert.equal(metadata.id, ref.artifactId, "artifact API ID differs");
  assert.equal(
    metadata.workflow_run?.id,
    Number(ref.runId),
    "artifact origin run differs",
  );
  assert.equal(
    metadata.workflow_run?.head_sha,
    ref.sourceCommit,
    "artifact origin source commit differs",
  );
  assert.equal(
    metadata.expired,
    false,
    "selected release artifact has expired",
  );
  assert.equal(
    metadata.digest,
    `sha256:${ref.zipSha256}`,
    "artifact API digest differs",
  );
  const runResponse = await fetchImpl(
    `https://api.github.com/repos/${repository}/actions/runs/${ref.runId}/attempts/${ref.runAttempt}`,
    { headers },
  );
  assert(
    runResponse.ok,
    `artifact origin run attempt lookup failed (${runResponse.status})`,
  );
  const runMetadata = await runResponse.json();
  assert.equal(
    runMetadata.id,
    Number(ref.runId),
    "artifact origin workflow run differs",
  );
  assert.equal(
    runMetadata.run_attempt,
    Number(ref.runAttempt),
    "artifact origin workflow attempt differs",
  );
  assert.equal(
    runMetadata.head_sha,
    ref.sourceCommit,
    "artifact origin workflow source differs",
  );
  assert.equal(
    runMetadata.head_branch,
    "swift",
    "artifact origin workflow branch differs",
  );
  assert.equal(
    runMetadata.event,
    "workflow_dispatch",
    "artifact origin is not a manual dispatch",
  );
  assert.equal(
    runMetadata.path,
    ".github/workflows/Publish-frontend-packages.yml",
    "artifact origin workflow path differs",
  );
  const zipResponse = await fetchImpl(`${endpoint}/zip`, { headers });
  assert(
    zipResponse.ok,
    `artifact ${ref.artifactId} ZIP download failed (${zipResponse.status})`,
  );
  const zip = Buffer.from(await zipResponse.arrayBuffer());
  assert.equal(sha256(zip), ref.zipSha256, "artifact ZIP SHA-256 differs");
  return { metadata, runMetadata, zip };
}

export async function extractReleaseArtifact({
  zip,
  expectedFiles,
  runCommand = run,
}) {
  const root = await mkdtemp(path.join(os.tmpdir(), "fred-release-artifact-"));
  try {
    const zipPath = path.join(root, "artifact.zip");
    await writeFile(zipPath, zip);
    const { stdout } = await runCommand("unzip", ["-Z", "-1", zipPath]);
    const names = stdout.trim().split("\n").filter(Boolean);
    if (expectedFiles)
      assert.deepEqual(
        names.sort(),
        [...expectedFiles].sort(),
        "retained artifact ZIP file set differs",
      );
    assert(
      names.every(
        (name) =>
          name &&
          !name.includes("/") &&
          !name.includes("\\") &&
          name !== "." &&
          name !== "..",
      ),
      "artifact ZIP contains an unsafe path",
    );
    await runCommand("unzip", ["-q", zipPath, "-d", root]);
    const entries = (await readdir(root)).filter(
      (name) => name !== "artifact.zip",
    );
    assert.deepEqual(
      entries.sort(),
      names.sort(),
      "extracted artifact file set differs",
    );
    for (const name of names)
      assert(
        (await lstat(path.join(root, name))).isFile(),
        `retained artifact ${name} must be a regular file, not a symbolic link or directory`,
      );
    return {
      root,
      names,
      cleanup: () => rm(root, { recursive: true, force: true }),
    };
  } catch (error) {
    await rm(root, { recursive: true, force: true });
    throw error;
  }
}

export function assertCandidateTransferBinding({
  metadataBytes,
  metadata,
  evidence,
  record,
}) {
  const digest = `sha256-${createHash("sha256").update(metadataBytes).digest("base64")}`;
  assert.equal(
    evidence.transfer?.metadataDigest,
    digest,
    "candidate evidence does not bind actual transfer metadata bytes",
  );
  assert.equal(
    record.transferOrigin?.metadataDigest,
    digest,
    "candidate record does not bind actual transfer metadata bytes",
  );
  for (const origin of [evidence.transfer, record.transferOrigin]) {
    assert.equal(
      origin.artifactName,
      metadata.artifactName,
      "candidate transfer artifact name differs",
    );
    assert.deepEqual(
      origin.execution,
      metadata.execution,
      "candidate transfer execution differs",
    );
  }
}

export async function verifyRetainedCandidate({ ref, artifact, contract }) {
  validateArtifactRef(ref);
  const metadataFilename = "candidate-transfer.json";
  const recordFilename = "candidate-record.json";
  const evidenceFilename = "candidate-evidence.json";
  const extracted = await extractReleaseArtifact({ zip: artifact.zip });
  try {
    const { root, names } = extracted;
    const metadataBytes = await readFile(path.join(root, metadataFilename));
    const metadata = JSON.parse(metadataBytes.toString("utf8"));
    const selectedIds =
      metadata.selectedIds ?? contract.inventory.members.map(({ id }) => id);
    const evidence = JSON.parse(
      await readFile(path.join(root, evidenceFilename), "utf8"),
    );
    const record = JSON.parse(
      await readFile(path.join(root, recordFilename), "utf8"),
    );
    assertCandidateTransferBinding({
      metadataBytes,
      metadata,
      evidence,
      record,
    });
    const archivePaths = Object.fromEntries(
      selectedIds.map((id) => [
        id,
        path.join(root, metadata.packages[id].filename),
      ]),
    );
    assert.deepEqual(
      names.sort(),
      [
        metadataFilename,
        evidenceFilename,
        recordFilename,
        ...Object.values(metadata.packages).map(({ filename }) => filename),
      ].sort(),
      "candidate artifact file set differs",
    );
    validateFixtureTransferMetadata(metadata, {
      contract,
      sourceCommit: record.sourceCommit,
      sourceTreeClean: true,
      execution: metadata.execution,
    });
    assert.equal(
      metadata.kind,
      "release-candidate-archive-transfer",
      "retained artifact is not an approved candidate",
    );
    assert.equal(
      metadata.execution.provider,
      "github-actions",
      "candidate must originate in GitHub Actions",
    );
    assert.equal(
      metadata.execution.runId,
      String(ref.runId),
      "candidate run differs",
    );
    assert.equal(
      metadata.execution.runAttempt,
      String(ref.runAttempt),
      "candidate attempt differs",
    );
    assert.equal(
      artifact.metadata.name,
      `frontend-packages-release-${record.sourceCommit}-${ref.runId}-${ref.runAttempt}`,
      "candidate API name differs",
    );
    assert.equal(
      artifact.metadata.workflow_run?.head_sha,
      record.sourceCommit,
      "candidate API source commit differs",
    );
    assert.equal(
      ref.sourceCommit,
      record.sourceCommit,
      "candidate input source commit differs",
    );
    await verifyCandidateEvidence(evidence, archivePaths, { contract });
    validateReleaseRecord(record);
    assert.equal(
      record.readiness,
      "complete",
      "candidate record is incomplete or fixture-labelled",
    );
    assert.equal(
      releaseRecordDigest(record),
      ref.recordDigest,
      "candidate record digest differs",
    );
    const rebuilt = await candidateRecordFromEvidence({
      evidence,
      contract,
      ledger: await loadCompatibilityLedger(),
      selectedIds,
      compatibilityOnly: record.compatibilityOnly.map(({ id }) => id),
      archivePaths,
    });
    assert.deepEqual(
      record,
      rebuilt,
      "candidate record differs from actual evidence and archives",
    );
    for (const id of selectedIds)
      assert.equal(
        await sha512Integrity(archivePaths[id]),
        record.archives[id].integrity,
        `${id} candidate archive differs`,
      );
    return {
      ...extracted,
      metadata,
      evidence,
      record,
      archivePaths,
      selectedIds,
    };
  } catch (error) {
    await extracted.cleanup();
    throw error;
  }
}

export async function verifyRetainedAttempt({
  ref,
  artifact,
  candidate,
  candidateRef,
  contract,
}) {
  validateArtifactRef(ref);
  const extracted = await extractReleaseArtifact({
    zip: artifact.zip,
    expectedFiles: ["publishing-attempt.json"],
  });
  try {
    const record = JSON.parse(
      await readFile(
        path.join(extracted.root, "publishing-attempt.json"),
        "utf8",
      ),
    );
    validateReleaseRecord(record);
    assert.equal(
      record.kind,
      "publishing-attempt",
      "artifact is not a publication attempt",
    );
    assert.equal(
      record.readiness,
      "persisted",
      "attempt artifact is not ready for readback",
    );
    assert.equal(
      releaseRecordDigest(record),
      ref.recordDigest,
      "attempt record digest differs",
    );
    assert.equal(
      record.candidateDigest,
      releaseRecordDigest(candidate),
      "attempt candidate digest differs",
    );
    assert.deepEqual(
      record.candidateArtifact,
      candidateRef,
      "attempt binds a different candidate artifact",
    );
    assert.equal(
      record.policyDigest,
      candidate.policyDigest,
      "attempt policy differs",
    );
    assert.equal(
      record.baselineDigest,
      candidate.baselineDigest,
      "attempt baseline differs",
    );
    assert.equal(
      record.execution.repository,
      "ThalesGroup/fred",
      "attempt repository differs",
    );
    assert.equal(
      record.execution.workflow,
      contract.workflowFilename,
      "attempt workflow differs",
    );
    assert.equal(
      record.execution.signerIssuer,
      contract.expectedProvenance.certificateIssuer,
      "attempt issuer differs",
    );
    assert.equal(
      record.execution.runId,
      String(ref.runId),
      "attempt origin run differs",
    );
    assert.equal(
      record.execution.runAttempt,
      String(ref.runAttempt),
      "attempt origin attempt differs",
    );
    assert.equal(
      artifact.metadata.workflow_run?.head_sha,
      record.execution.sourceCommit,
      "attempt API commit differs",
    );
    assert.equal(
      ref.sourceCommit,
      record.execution.sourceCommit,
      "attempt input commit differs",
    );
    assert.equal(
      artifact.metadata.name,
      `frontend-packages-attempt-${record.execution.sourceCommit}-${ref.runId}-${ref.runAttempt}`,
      "attempt API name differs",
    );
    assert.deepEqual(
      record.selected,
      candidate.selected.map(({ id, coordinate }) => ({
        id,
        coordinate,
        integrity: candidate.archives[id].integrity,
      })),
      "attempt selected archive set differs",
    );
    return { ...extracted, record, ref };
  } catch (error) {
    await extracted.cleanup();
    throw error;
  }
}

export function assertTerminalJobBoundary({ run, jobs, terminal, attempt }) {
  assert.equal(run.status, "completed", "publishing attempt is not complete");
  assert.equal(
    run.conclusion,
    "failure",
    "terminal requires a failed completed publishing attempt",
  );
  assert.equal(
    jobs.total_count,
    jobs.jobs?.length,
    "publishing job history is incomplete or paginated",
  );
  const publishingJobs = jobs.jobs.filter(({ name }) => name === "publish");
  assert.equal(
    publishingJobs.length,
    1,
    "publishing job history is incomplete or ambiguous",
  );
  const [job] = publishingJobs;
  assert.equal(
    job.run_id,
    Number(attempt.execution.runId),
    "terminal job run differs",
  );
  assert.equal(
    job.head_sha,
    attempt.execution.sourceCommit,
    "terminal job source differs",
  );
  assert.equal(job.status, "completed", "publishing job remains unresolved");
  assert.equal(job.conclusion, "failure", "publishing job did not abort");
  const executionStep = job.steps?.find(
    ({ name }) =>
      name === "Read back attempt and publish demonstrably absent archives",
  );
  const terminalStep = job.steps?.find(
    ({ name }) => name === "Durably retain aborted publishing boundaries",
  );
  assert.equal(
    executionStep?.status,
    "completed",
    "publishing step is unresolved",
  );
  assert.equal(
    executionStep?.conclusion,
    "failure",
    "publishing step did not abort",
  );
  assert.equal(
    terminalStep?.status,
    "completed",
    "terminal upload step is unresolved",
  );
  assert.equal(
    terminalStep?.conclusion,
    "success",
    "terminal upload was not successful",
  );
  assert(
    terminalStep.number > executionStep.number,
    "terminal was retained before the publishing step stopped",
  );
  assert.deepEqual(
    terminal.passedBoundaries.concat(terminal.neverInvoked),
    attempt.selected.map(({ id }) => id),
    "terminal does not cover the exact serialized selection",
  );
  assert(
    job.steps.every(
      ({ name, number, status }) =>
        number <= executionStep.number ||
        name === "Durably retain aborted publishing boundaries" ||
        status !== "completed" ||
        !/npm publish|publish demonstrably absent archives/i.test(name),
    ),
    "a later publication path exists after the terminal boundary",
  );
}

export async function verifyRetainedTerminal({
  ref,
  artifact,
  attempt,
  candidateRef,
  token,
  fetchImpl = fetch,
}) {
  validateArtifactRef(ref);
  const extracted = await extractReleaseArtifact({
    zip: artifact.zip,
    expectedFiles: ["publishing-terminal.json"],
  });
  try {
    const record = JSON.parse(
      await readFile(
        path.join(extracted.root, "publishing-terminal.json"),
        "utf8",
      ),
    );
    validateReleaseRecord(record);
    assert.equal(
      record.kind,
      "publishing-terminal",
      "artifact is not a publishing terminal",
    );
    assert.equal(
      releaseRecordDigest(record),
      ref.recordDigest,
      "terminal record digest differs",
    );
    assert.equal(
      record.attemptDigest,
      releaseRecordDigest(attempt.record),
      "terminal attempt digest differs",
    );
    assert.equal(
      record.candidateDigest,
      attempt.record.candidateDigest,
      "terminal candidate digest differs",
    );
    assert.deepEqual(
      record.candidateArtifact,
      candidateRef,
      "terminal candidate reference differs",
    );
    assert.deepEqual(
      record.execution,
      attempt.record.execution,
      "terminal execution differs",
    );
    assert.equal(
      ref.runId,
      attempt.ref.runId,
      "terminal run differs from attempt",
    );
    assert.equal(
      ref.runAttempt,
      attempt.ref.runAttempt,
      "terminal run attempt differs",
    );
    assert.equal(
      ref.sourceCommit,
      attempt.ref.sourceCommit,
      "terminal commit differs",
    );
    assert.equal(
      artifact.metadata.name,
      `frontend-packages-terminal-${record.execution.sourceCommit}-${ref.runId}-${ref.runAttempt}`,
      "terminal API name differs",
    );
    assert(
      token,
      "GITHUB_TOKEN is required for completed-run boundary verification",
    );
    const response = await fetchImpl(
      `https://api.github.com/repos/ThalesGroup/fred/actions/runs/${ref.runId}/attempts/${ref.runAttempt}/jobs?per_page=100`,
      {
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: "application/vnd.github+json",
          "X-GitHub-Api-Version": "2022-11-28",
        },
      },
    );
    assert(
      response.ok,
      `publishing attempt jobs lookup failed (${response.status})`,
    );
    assertTerminalJobBoundary({
      run: artifact.runMetadata,
      jobs: await response.json(),
      terminal: record,
      attempt: attempt.record,
    });
    return { ...extracted, record, ref, verifiedBoundary: true };
  } catch (error) {
    await extracted.cleanup();
    throw error;
  }
}

export async function assertCompleteCandidateAttemptHistory({
  candidate,
  candidateRef,
  candidateMetadata,
  candidateRunMetadata,
  historyLowerBound,
  currentRef,
  priorRefs,
  token,
  fetchImpl = fetch,
}) {
  assert(
    token,
    "GITHUB_TOKEN is required to enumerate retained publishing attempts",
  );
  const origin = Date.parse(candidateMetadata.created_at);
  assert(
    Number.isFinite(origin),
    "candidate artifact creation time is unavailable",
  );
  const runOrigin = Date.parse(candidateRunMetadata?.created_at);
  assert(
    Number.isFinite(runOrigin) && runOrigin <= origin,
    "candidate origin run creation time is unavailable or follows artifact creation",
  );
  assert.equal(
    candidateRunMetadata.id,
    Number(candidateRef.runId),
    "candidate origin run identity differs",
  );
  const historyOrigin = Date.parse(historyLowerBound);
  assert(
    Number.isFinite(historyOrigin) &&
      historyOrigin >= publishingWorkflowEpoch &&
      historyOrigin <= runOrigin,
    "reviewed selected-coordinate history boundary is missing or follows candidate creation",
  );
  const headers = {
    Authorization: `Bearer ${token}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
  };
  const found = [];
  const visibleRuns = new Set();
  const selectedCoordinates = new Set(
    candidate.selected.map(({ coordinate }) => coordinate),
  );
  const crossCandidateCoordinates = [];
  let total;
  for (let page = 1; ; page++) {
    assert(
      page <= 100,
      "publishing attempt artifact enumeration exceeded the reviewed bound",
    );
    const response = await fetchImpl(
      `https://api.github.com/repos/ThalesGroup/fred/actions/artifacts?per_page=100&page=${page}`,
      { headers },
    );
    assert(
      response.ok,
      `publishing attempt artifact enumeration failed (${response.status})`,
    );
    const listing = await response.json();
    assert(
      Array.isArray(listing.artifacts) &&
        Number.isSafeInteger(listing.total_count),
      "publishing attempt artifact listing is malformed",
    );
    if (total === undefined) total = listing.total_count;
    assert.equal(
      listing.total_count,
      total,
      "publishing attempt artifact listing changed during enumeration",
    );
    for (const metadata of listing.artifacts) {
      if (
        !/^frontend-packages-attempt-/.test(metadata.name ?? "") ||
        Date.parse(metadata.created_at) < historyOrigin
      )
        continue;
      assert.equal(
        metadata.expired,
        false,
        "a retained publishing attempt artifact expired; history is incomplete",
      );
      assert(
        /^sha256:[a-f0-9]{64}$/.test(metadata.digest),
        "publishing attempt API digest is malformed",
      );
      const zipResponse = await fetchImpl(
        `https://api.github.com/repos/ThalesGroup/fred/actions/artifacts/${metadata.id}/zip`,
        { headers },
      );
      assert(
        zipResponse.ok,
        `publishing attempt ${metadata.id} ZIP is unavailable; history is incomplete`,
      );
      const zip = Buffer.from(await zipResponse.arrayBuffer());
      assert.equal(
        sha256(zip),
        metadata.digest.slice(7),
        "enumerated publishing attempt ZIP differs from API digest",
      );
      const extracted = await extractReleaseArtifact({
        zip,
        expectedFiles: ["publishing-attempt.json"],
      });
      try {
        const record = JSON.parse(
          await readFile(
            path.join(extracted.root, "publishing-attempt.json"),
            "utf8",
          ),
        );
        validateReleaseRecord(record);
        assert.equal(
          record.execution.runId,
          String(metadata.workflow_run?.id),
          "enumerated attempt run differs",
        );
        assert.equal(
          record.execution.sourceCommit,
          metadata.workflow_run?.head_sha,
          "enumerated attempt source differs",
        );
        visibleRuns.add(
          `${record.execution.runId}/${record.execution.runAttempt}`,
        );
        if (record.candidateDigest !== releaseRecordDigest(candidate)) {
          if (
            record.selected.some(({ coordinate }) =>
              selectedCoordinates.has(coordinate),
            )
          )
            crossCandidateCoordinates.push(metadata.id);
          continue;
        }
        assert.deepEqual(
          record.candidateArtifact,
          candidateRef,
          "enumerated attempt candidate reference differs",
        );
        found.push(metadata.id);
      } finally {
        await extracted.cleanup();
      }
    }
    if (page * 100 >= total) break;
    assert(
      listing.artifacts.length === 100,
      "publishing attempt artifact pagination is incomplete",
    );
  }
  assert.deepEqual(
    found.sort((a, b) => a - b),
    [currentRef, ...priorRefs]
      .map(({ artifactId }) => artifactId)
      .sort((a, b) => a - b),
    "manual attempt references omit or add a retained publishing attempt; history is incomplete",
  );
  assert.deepEqual(
    crossCandidateCoordinates,
    [],
    "selected coordinate has an attempt bound to another retained candidate; fresh candidate publication could repeat a command",
  );
  const candidateDate = new Date(historyOrigin).toISOString();
  let runTotal;
  let sawCandidateRun = false;
  for (let page = 1; ; page++) {
    assert(
      page <= 100,
      "publishing workflow run history exceeded the reviewed bound",
    );
    const endpoint = `https://api.github.com/repos/ThalesGroup/fred/actions/workflows/Publish-frontend-packages.yml/runs?branch=swift&event=workflow_dispatch&created=${encodeURIComponent(`>=${candidateDate}`)}&per_page=100&page=${page}`;
    const response = await fetchImpl(endpoint, { headers });
    assert(
      response.ok,
      `publishing workflow run history lookup failed (${response.status})`,
    );
    const listing = await response.json();
    assert(
      Array.isArray(listing.workflow_runs) &&
        Number.isSafeInteger(listing.total_count),
      "publishing workflow run history is malformed",
    );
    if (runTotal === undefined) runTotal = listing.total_count;
    assert(
      runTotal < 1000,
      "publishing workflow run search hit GitHub's 1000-run cap; history is incomplete",
    );
    assert.equal(
      listing.total_count,
      runTotal,
      "publishing workflow run history changed during enumeration",
    );
    for (const workflowRun of listing.workflow_runs) {
      assert(
        Number.isSafeInteger(workflowRun.id) &&
          Number.isSafeInteger(workflowRun.run_attempt) &&
          workflowRun.run_attempt > 0,
        "publishing workflow run identity is incomplete",
      );
      assert.equal(
        workflowRun.head_branch,
        "swift",
        "publishing workflow run branch differs",
      );
      assert.equal(
        workflowRun.event,
        "workflow_dispatch",
        "publishing workflow run event differs",
      );
      if (workflowRun.id === Number(candidateRef.runId)) sawCandidateRun = true;
      for (
        let runAttempt = 1;
        runAttempt <= workflowRun.run_attempt;
        runAttempt++
      ) {
        const jobsResponse = await fetchImpl(
          `https://api.github.com/repos/ThalesGroup/fred/actions/runs/${workflowRun.id}/attempts/${runAttempt}/jobs?per_page=100`,
          { headers },
        );
        assert(
          jobsResponse.ok,
          `publishing workflow jobs for ${workflowRun.id}/${runAttempt} are unavailable`,
        );
        const jobs = await jobsResponse.json();
        assert(
          Array.isArray(jobs.jobs) && jobs.total_count === jobs.jobs.length,
          "publishing workflow job history is incomplete or paginated",
        );
        const publishJobs = jobs.jobs.filter(({ name }) => name === "publish");
        assert(
          publishJobs.length <= 1,
          "publishing workflow job history has multiple publication paths",
        );
        const job = publishJobs[0];
        if (!job) continue;
        const upload = job.steps?.find(
          ({ name }) => name === "Durably retain pre-command attempt",
        );
        const execute = job.steps?.find(
          ({ name }) =>
            name ===
            "Read back attempt and publish demonstrably absent archives",
        );
        if (
          upload?.conclusion === "success" ||
          execute?.status === "completed" ||
          execute?.status === "in_progress"
        ) {
          assert(
            visibleRuns.has(`${workflowRun.id}/${runAttempt}`),
            `publishing workflow ${workflowRun.id}/${runAttempt} crossed an attempt boundary without its retained artifact; history is incomplete`,
          );
          assert(
            job.status === "completed" ||
              `${workflowRun.id}/${runAttempt}` ===
                `${currentRef.runId}/${currentRef.runAttempt}`,
            "a prior publishing execution remains unresolved",
          );
        }
      }
    }
    if (page * 100 >= runTotal) break;
    assert(
      listing.workflow_runs.length === 100,
      "publishing workflow run pagination is incomplete",
    );
  }
  assert(
    sawCandidateRun,
    "candidate origin workflow run is missing from independent run history",
  );
  return found;
}

export function uploadedArtifactRef({
  artifactId,
  artifactDigest,
  recordDigest,
  runId,
  runAttempt,
  sourceCommit,
}) {
  assert(
    /^[a-f0-9]{64}$/.test(artifactDigest),
    "uploaded artifact digest is malformed",
  );
  return validateArtifactRef({
    artifactId: Number(artifactId),
    zipSha256: artifactDigest,
    recordDigest,
    runId: String(runId),
    runAttempt: String(runAttempt),
    sourceCommit,
  });
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const command = process.argv[2];
  if (command === "record-digest") {
    const record = JSON.parse(await readFile(process.argv[3], "utf8"));
    const value = releaseRecordDigest(record);
    if (process.env.GITHUB_OUTPUT)
      await appendFile(process.env.GITHUB_OUTPUT, `record_digest=${value}\n`);
    process.stdout.write(`${value}\n`);
  } else if (command === "uploaded-ref") {
    const ref = uploadedArtifactRef({
      artifactId: process.env.RELEASE_UPLOADED_ID,
      artifactDigest: process.env.RELEASE_UPLOADED_DIGEST,
      recordDigest: process.env.RELEASE_RECORD_DIGEST,
      runId: process.env.GITHUB_RUN_ID,
      runAttempt: process.env.GITHUB_RUN_ATTEMPT,
      sourceCommit: process.env.GITHUB_SHA,
    });
    if (process.env.GITHUB_OUTPUT)
      await appendFile(
        process.env.GITHUB_OUTPUT,
        `ref=${JSON.stringify(ref)}\n`,
      );
    process.stdout.write(`${JSON.stringify(ref)}\n`);
  } else if (command === "print-ref") {
    const ref = validateArtifactRef(
      JSON.parse(process.env.RELEASE_CANDIDATE_REF ?? "null"),
    );
    if (process.env.GITHUB_OUTPUT)
      await appendFile(
        process.env.GITHUB_OUTPUT,
        `ref=${JSON.stringify(ref)}\n`,
      );
    process.stdout.write(`${JSON.stringify(ref)}\n`);
  } else
    throw new Error(
      "release-artifact command must be record-digest, uploaded-ref, or print-ref",
    );
}

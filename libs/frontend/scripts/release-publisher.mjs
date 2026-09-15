import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { validateArtifactRef } from "./release-dispatch.mjs";
import {
  retrieveReleaseArtifact,
  verifyRetainedAttempt,
  verifyRetainedTerminal,
  assertCompleteCandidateAttemptHistory,
  verifyRetainedCandidate,
} from "./release-artifact.mjs";
import { loadReleaseContract, workspaceRoot } from "./release-contract.mjs";
import { selectReleaseMembers } from "./release-selection.mjs";
import { checkTransferChangelogs } from "./fixture-transfer.mjs";
import {
  fetchExactPackageMetadata,
  waitForExactPackageMetadata,
} from "./registry-metadata.mjs";
import {
  releasePolicyDigest,
  releaseRecordDigest,
  publishingAttemptModel,
  publishingTerminalModel,
  assertRecordAuthorizesPublication,
  publicationOutcomeModel,
} from "./release-record.mjs";
import {
  matchVerifiedPublishingAttempt,
  resolveNpmRegistryPackage,
  verifyNpmPackageProvenance,
} from "./registry-verifier.mjs";
import { run } from "./process.mjs";
import { assertDocumentSchema } from "./schema-validation.mjs";

export function currentPublishingExecution(environment, contract) {
  assert.equal(
    environment.GITHUB_REPOSITORY,
    "ThalesGroup/fred",
    "publishing repository differs from policy",
  );
  assert.equal(
    environment.GITHUB_REF,
    `refs/heads/${contract.sourceBranch}`,
    "publishing branch differs from policy",
  );
  assert.equal(
    environment.GITHUB_WORKFLOW_REF,
    `ThalesGroup/fred/.github/workflows/${contract.workflowFilename}@${environment.GITHUB_REF}`,
    "publishing workflow identity differs from policy",
  );
  assert(
    /^[a-f0-9]{40}$/.test(environment.GITHUB_SHA ?? ""),
    "publishing commit is not exact",
  );
  assert(
    /^[1-9]\d*$/.test(environment.GITHUB_RUN_ID ?? "") &&
      /^[1-9]\d*$/.test(environment.GITHUB_RUN_ATTEMPT ?? ""),
    "publishing run identity is incomplete",
  );
  return {
    repository: environment.GITHUB_REPOSITORY,
    workflow: contract.workflowFilename,
    sourceCommit: environment.GITHUB_SHA,
    runId: environment.GITHUB_RUN_ID,
    runAttempt: environment.GITHUB_RUN_ATTEMPT,
    signerIssuer: contract.expectedProvenance.certificateIssuer,
  };
}

export function assertRetainedCandidateSelection(
  candidate,
  contract,
  selection,
) {
  assert.deepEqual(
    candidate.selectedIds,
    selectReleaseMembers(contract, selection),
    "manual selection differs from retained candidate; no package may be published",
  );
}

export async function reviewedCoordinateHistoryStart(
  candidate,
  contract,
  runCommand = run,
  { token, fetchImpl = fetch } = {},
) {
  assert(
    token,
    "GITHUB_TOKEN is required for independently observed changelog merge history",
  );
  const { stdout: shallowState } = await runCommand(
    "git",
    ["rev-parse", "--is-shallow-repository"],
    { cwd: workspaceRoot },
  );
  assert.equal(
    shallowState.trim(),
    "false",
    "publication requires complete Git history for reviewed coordinates",
  );
  const dates = [];
  for (const selected of candidate.selected) {
    const member = contract.inventory.members.find(
      ({ id }) => id === selected.id,
    );
    assert(
      member,
      `selected coordinate ${selected.id} has no registered changelog`,
    );
    const version = selected.coordinate.slice(
      selected.coordinate.lastIndexOf("@") + 1,
    );
    assert.equal(
      version,
      contract.packages[selected.id].version,
      "selected coordinate version differs from reviewed manifest",
    );
    const changelog = `libs/frontend/${member.workspace}/CHANGELOG.md`;
    const exactHeading = `^## ${version.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}$`;
    const { stdout } = await runCommand(
      "git",
      [
        "log",
        "--reverse",
        "--format=%H %aI %cI",
        "-G",
        exactHeading,
        "--",
        `${member.workspace}/CHANGELOG.md`,
      ],
      { cwd: workspaceRoot },
    );
    const introduction = stdout.trim().split("\n")[0]?.split(" ");
    assert(
      introduction?.length === 3 && /^[a-f0-9]{40}$/.test(introduction[0]),
      `${selected.coordinate} has no exact reviewed changelog introduction commit`,
    );
    const [{ stdout: introducedText }] = await Promise.all([
      runCommand("git", ["show", `${introduction[0]}:${changelog}`], {
        cwd: workspaceRoot,
      }),
      runCommand(
        "git",
        [
          "merge-base",
          "--is-ancestor",
          introduction[0],
          candidate.sourceCommit,
        ],
        { cwd: workspaceRoot },
      ),
    ]);
    assert(
      introducedText.split("\n").includes(`## ${version}`),
      `${selected.coordinate} history boundary did not introduce its exact changelog heading`,
    );
    const timestamps = introduction.slice(1).map((value) => Date.parse(value));
    assert(
      timestamps.every(Number.isFinite),
      `${selected.coordinate} changelog history dates are invalid`,
    );
    const response = await fetchImpl(
      `https://api.github.com/repos/ThalesGroup/fred/commits/${introduction[0]}/pulls`,
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
      `${selected.coordinate} reviewed merge lookup failed (${response.status})`,
    );
    const pulls = await response.json();
    assert(
      Array.isArray(pulls),
      `${selected.coordinate} reviewed merge response is malformed`,
    );
    const merged = [];
    for (const pull of pulls) {
      if (
        pull.base?.ref !== contract.sourceBranch ||
        !pull.merged_at ||
        !/^[a-f0-9]{40}$/.test(pull.merge_commit_sha ?? "")
      )
        continue;
      try {
        await runCommand(
          "git",
          [
            "merge-base",
            "--is-ancestor",
            pull.merge_commit_sha,
            candidate.sourceCommit,
          ],
          { cwd: workspaceRoot },
        );
      } catch {
        continue;
      }
      const observed = Date.parse(pull.merged_at);
      assert(
        Number.isFinite(observed),
        `${selected.coordinate} GitHub merge timestamp is invalid`,
      );
      merged.push(observed);
    }
    assert(
      merged.length,
      `${selected.coordinate} has no independently observed merged swift PR containing its reviewed changelog introduction`,
    );
    dates.push(Math.min(...timestamps, ...merged));
  }
  assert(dates.length, "selected-coordinate history is empty");
  return new Date(Math.min(...dates)).toISOString();
}

export async function loadKnownPublishedCoordinates(
  filename = path.join(
    workspaceRoot,
    "release/known-published-coordinates.json",
  ),
) {
  const ledger = JSON.parse(await readFile(filename, "utf8"));
  assertDocumentSchema(
    ledger,
    path.join(workspaceRoot, "release/known-published-coordinates.schema.json"),
    "known published coordinates",
  );
  assert.equal(
    new Set(ledger.packages.map(({ coordinate }) => coordinate)).size,
    ledger.packages.length,
    "known published coordinates contain duplicates",
  );
  const runbook = await readFile(
    path.join(workspaceRoot, "RELEASE.md"),
    "utf8",
  );
  const historical = [
    ...runbook.matchAll(
      /^\|\s*`([^`]+)`\s*\|\s*`(sha512-[^`]+)`\s*\|\s*`([a-f0-9]{40})`\s*\|$/gm,
    ),
  ].map(([, coordinate, integrity, publicationCommit]) => ({
    coordinate,
    integrity,
    publicationCommit,
  }));
  assert(
    historical.length > 0,
    "reviewed historical release appendix is missing",
  );
  assert.deepEqual(
    ledger.packages,
    historical,
    "known published ledger differs from source-reviewed historical release appendix",
  );
  assert(
    runbook.includes(
      `read-only verification run \`${ledger.historicalVerification.runId}\`, attempt \`${ledger.historicalVerification.runAttempt}\``,
    ) &&
      runbook.includes(
        `artifact \`${ledger.historicalVerification.artifactId}\``,
      ) &&
      runbook.includes(ledger.historicalVerification.artifactZipSha256),
    "known published ledger verification trace differs from historical release appendix",
  );
  return ledger;
}

export function assertNoKnownPublishedSelection(candidate, ledger) {
  for (const member of candidate.selected) {
    const known = ledger.packages.find(
      ({ coordinate }) => coordinate === member.coordinate,
    );
    assert(
      !known,
      `${member.coordinate} is recorded as already published by historical verified release evidence; temporary registry invisibility cannot authorize a fresh publish`,
    );
  }
}

export async function reconcileSelected({
  candidate,
  registry,
  readExact = fetchExactPackageMetadata,
  verifyExisting,
  priorAttempts = [],
  verifiedTerminals = [],
  visibilityAttempts = 6,
  wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
}) {
  const states = {};
  for (const member of candidate.selected) {
    const expected = {
      coordinate: member.coordinate,
      integrity: candidate.archives[member.id].integrity,
    };
    let metadata = null;
    for (let attempt = 1; attempt <= visibilityAttempts; attempt++) {
      metadata = await readExact({
        coordinate: member.coordinate,
        registry,
        candidate: expected,
      });
      if (metadata) break;
      if (attempt < visibilityAttempts) await wait(2000);
    }
    if (!metadata) {
      const relevant = priorAttempts.filter(({ record }) =>
        record.selected.some(({ id }) => id === member.id),
      );
      assert(
        relevant.every(({ record }) =>
          verifiedTerminals.some(
            ({ record: terminal, verifiedBoundary }) =>
              verifiedBoundary === true &&
              terminal.attemptDigest === releaseRecordDigest(record) &&
              terminal.neverInvoked.includes(member.id),
          ),
        ),
        `${member.coordinate} visibility is unresolved after a retained publishing attempt; do not repeat publication`,
      );
      states[member.id] = "absent";
      continue;
    }
    const authorized = priorAttempts.filter(({ record }) =>
      record.selected.some(({ id }) => id === member.id),
    );
    assert(
      authorized.length,
      `${member.coordinate} already exists without a retained outcome or pre-command attempt`,
    );
    const verified = await verifyExisting({
      member,
      expected,
      metadata,
      authorized,
    });
    assert(
      verified?.cryptographicallyVerified,
      `${member.coordinate} existing version lacks matching cryptographic provenance`,
    );
    states[member.id] = "matching";
  }
  return states;
}

export async function verifyPublishedMember({
  member,
  expected,
  contract,
  attempts,
  resolvePackage = resolveNpmRegistryPackage,
  verifySignature = verifyNpmPackageProvenance,
}) {
  const root = await mkdtemp(path.join(os.tmpdir(), "fred-published-release-"));
  try {
    const evidence = { packages: { [member.id]: expected } };
    const registryPackage = await resolvePackage({
      coordinate: expected.coordinate,
      registry: contract.registry,
      root,
      role: member.id,
      contract,
      evidence,
      expectedPackage: contract.packages[member.id],
      candidate: expected,
    });
    assert.equal(
      registryPackage.integrity,
      expected.integrity,
      `${expected.coordinate} downloaded registry archive integrity differs`,
    );
    const expectationList = attempts.filter(({ record }) =>
      record.selected.some(({ id }) => id === member.id),
    );
    assert(
      expectationList.length,
      `${expected.coordinate} has no retained publishing attempt`,
    );
    const signature = await verifySignature(registryPackage, {
      registry: contract.registry,
      expectedProvenance: {
        repository: contract.expectedProvenance.repository,
        workflow: contract.expectedProvenance.workflow,
      },
      certificateIssuer: contract.expectedProvenance.certificateIssuer,
    });
    const matchingAttempt = matchVerifiedPublishingAttempt({
      signature,
      expectedProvenance: {
        artifactDigest: expected.integrity,
        repository: contract.expectedProvenance.repository,
        workflow: contract.expectedProvenance.workflow,
      },
      publicationAttempts: expectationList,
      memberId: member.id,
    });
    return {
      cryptographicallyVerified: true,
      identity: signature.identity,
      attempt: matchingAttempt,
    };
  } finally {
    await rm(root, { recursive: true, force: true });
  }
}

export async function executeOrdinaryPublication({
  candidate,
  candidateRef,
  attempt,
  attemptRef,
  priorAttempts,
  verifiedTerminals = [],
  contract,
  archivePaths,
  publishCommand = run,
  readExact,
  verifyExisting = verifyPublishedMember,
  wait,
  verifyIntent,
  onTerminal = async () => {},
  knownPublished,
}) {
  assert.equal(
    candidate.policyDigest,
    releasePolicyDigest(contract),
    "candidate policy differs from current approved policy",
  );
  if (typeof verifyIntent !== "function") {
    throw new Error(
      "publication requires retained per-package intent readback",
    );
  }
  if (!knownPublished || !Array.isArray(knownPublished.packages)) {
    throw new Error("publication requires the reviewed known-published ledger");
  }
  assertNoKnownPublishedSelection(candidate, knownPublished);
  assertRecordAuthorizesPublication(attempt, {
    candidate,
    readback: { recordDigest: attemptRef.recordDigest, candidateRef },
  });
  assert.deepEqual(
    attempt.selected,
    candidate.selected.map(({ id, coordinate }) => ({
      id,
      coordinate,
      integrity: candidate.archives[id].integrity,
    })),
    "attempt selected package set differs",
  );
  const possiblyInvoked = [];
  const passedBoundaries = [];
  const retainAbort = async (error) => {
    if (passedBoundaries.length < candidate.selected.length)
      await onTerminal(
        publishingTerminalModel({ attempt, passedBoundaries, possiblyInvoked }),
      );
    throw error;
  };
  let states;
  try {
    states = await reconcileSelected({
      candidate,
      registry: contract.registry,
      readExact,
      verifyExisting: (input) =>
        verifyExisting({
          ...input,
          candidate,
          contract,
          attempts: priorAttempts,
        }),
      priorAttempts,
      verifiedTerminals,
      wait,
    });
  } catch (error) {
    return retainAbort(error);
  }
  const outcomes = [];
  try {
    for (const member of candidate.selected) {
      if (states[member.id] === "matching") {
        passedBoundaries.push(member.id);
        continue;
      }
      if (
        member.id === "ui" &&
        candidate.selected.some(({ id }) => id === "designTokens")
      ) {
        assert(
          ["matching", "published"].includes(states.designTokens),
          "selected design tokens must be verified before UI publication",
        );
      }
      const archivePath = archivePaths[member.id];
      await verifyIntent({
        member,
        attempt,
        attemptRef,
        candidate,
        candidateRef,
      });
      assert.equal(
        path.basename(archivePath),
        candidate.archives[member.id].filename,
        `${member.id} exact archive filename differs`,
      );
      const { sha512Integrity } = await import("./release-evidence.mjs");
      assert.equal(
        await sha512Integrity(archivePath),
        candidate.archives[member.id].integrity,
        `${member.id} exact archive bytes differ before publication`,
      );
      const configRoot = await mkdtemp(
        path.join(os.tmpdir(), "fred-oidc-config-"),
      );
      try {
        const userConfig = path.join(configRoot, "user.npmrc");
        const globalConfig = path.join(configRoot, "global.npmrc");
        await writeFile(userConfig, "", { flag: "wx" });
        await writeFile(globalConfig, "", { flag: "wx" });
        const publishEnvironment = {
          ...process.env,
          NPM_CONFIG_USERCONFIG: userConfig,
          NPM_CONFIG_GLOBALCONFIG: globalConfig,
        };
        for (const key of [
          "NODE_AUTH_TOKEN",
          "NPM_TOKEN",
          "NPM_BOOTSTRAP_TOKEN",
          "NPM_CONFIG__AUTH",
          "NPM_CONFIG__AUTH_TOKEN",
          "GITHUB_TOKEN",
        ])
          delete publishEnvironment[key];
        possiblyInvoked.push(member.id);
        passedBoundaries.push(member.id);
        await publishCommand(
          "npm",
          [
            "publish",
            archivePath,
            "--tag",
            contract.distTag,
            "--access",
            contract.maintainerApproval.registryAccess,
            "--provenance",
            "--registry",
            contract.registry,
          ],
          { cwd: path.dirname(archivePath), env: publishEnvironment },
        );
      } finally {
        await rm(configRoot, { recursive: true, force: true });
      }
      await waitForExactPackageMetadata({
        candidate: {
          coordinate: member.coordinate,
          integrity: candidate.archives[member.id].integrity,
        },
        registry: contract.registry,
        inspectRegistry: readExact,
        waitForVisibility: wait,
      });
      const verified = await verifyExisting({
        member,
        expected: {
          coordinate: member.coordinate,
          integrity: candidate.archives[member.id].integrity,
        },
        candidate,
        contract,
        attempts: [{ record: attempt, ref: attemptRef }],
      });
      assert(
        verified?.cryptographicallyVerified,
        `${member.coordinate} publication outcome is not independently verified`,
      );
      const outcome = publicationOutcomeModel({
        attempt,
        memberId: member.id,
        coordinate: member.coordinate,
        integrity: candidate.archives[member.id].integrity,
        provenance: { ...verified.identity, cryptographicallyVerified: true },
      });
      outcome.readiness = "verified";
      outcomes.push(outcome);
      states[member.id] = "published";
    }
  } catch (error) {
    return retainAbort(error);
  }
  return { states, outcomes };
}

async function loadCandidate(ref, contract, token) {
  const artifact = await retrieveReleaseArtifact({
    ref,
    repository: "ThalesGroup/fred",
    token,
  });
  return {
    ...(await verifyRetainedCandidate({ ref, artifact, contract })),
    artifactMetadata: artifact.metadata,
    artifactRunMetadata: artifact.runMetadata,
  };
}

function jsonEnvironment(name) {
  const value = process.env[name];
  assert(value, `${name} is required`);
  return JSON.parse(value);
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const phase = process.argv[2];
  assert(
    ["prepare-attempt", "execute"].includes(phase),
    "publisher phase must be prepare-attempt or execute",
  );
  const contract = await loadReleaseContract(
    "release/proposed-release-contract.json",
  );
  assert.equal(
    contract.state,
    "maintainer-confirmed",
    "publication policy is incomplete",
  );
  const execution = currentPublishingExecution(process.env, contract);
  const candidateRef = validateArtifactRef(
    jsonEnvironment("RELEASE_CANDIDATE_REF"),
  );
  const candidate = await loadCandidate(
    candidateRef,
    contract,
    process.env.GITHUB_TOKEN,
  );
  try {
    assertRetainedCandidateSelection(
      candidate,
      contract,
      process.env.RELEASE_SELECTION,
    );
    assert.equal(
      candidate.record.policyDigest,
      releasePolicyDigest(contract),
      "retained policy differs from approved release policy",
    );
    const [{ stdout: checkedOutCommit }, { stdout: sourceStatus }] =
      await Promise.all([
        run("git", ["rev-parse", "HEAD"], { cwd: workspaceRoot }),
        run("git", ["status", "--porcelain"], { cwd: workspaceRoot }),
      ]);
    assert.equal(
      checkedOutCommit.trim(),
      execution.sourceCommit,
      "checked-out controller differs from actual workflow execution commit",
    );
    assert.equal(
      sourceStatus.trim(),
      "",
      "publication requires a clean reviewed source checkout",
    );
    await checkTransferChangelogs(
      contract,
      workspaceRoot,
      candidate.selectedIds,
    );
    if (phase === "prepare-attempt") {
      const record = publishingAttemptModel({
        candidate: candidate.record,
        execution,
        candidateArtifact: candidateRef,
      });
      const outputPath = process.env.RELEASE_ATTEMPT_PATH;
      assert(outputPath, "RELEASE_ATTEMPT_PATH is required");
      await mkdir(path.dirname(outputPath), { recursive: true });
      await writeFile(outputPath, `${JSON.stringify(record, null, 2)}\n`, {
        flag: "wx",
      });
      process.stdout.write(
        `${JSON.stringify({ recordDigest: releaseRecordDigest(record) })}\n`,
      );
    } else {
      assert.equal(
        process.env.GITHUB_ACTIONS,
        "true",
        "publication requires GitHub-hosted Actions",
      );
      assert(
        Object.hasOwn(process.env, "ACTIONS_ID_TOKEN_REQUEST_URL") &&
          Object.hasOwn(process.env, "ACTIONS_ID_TOKEN_REQUEST_TOKEN"),
        "direct OIDC publication prerequisites are missing",
      );
      for (const name of Object.keys(process.env))
        if (
          /^(?:NPM|npm|NODE_AUTH).*?(?:AUTH|TOKEN|PASSWORD|_PASSWORD)$/i.test(
            name,
          ) ||
          ["NODE_AUTH_TOKEN", "NPM_TOKEN", "NPM_BOOTSTRAP_TOKEN"].includes(name)
        )
          assert.fail(
            `publication credential variable ${name} must not be present`,
          );
      const attemptRef = validateArtifactRef(
        jsonEnvironment("RELEASE_CURRENT_ATTEMPT_REF"),
      );
      const attempt = await verifyRetainedAttempt({
        ref: attemptRef,
        artifact: await retrieveReleaseArtifact({
          ref: attemptRef,
          repository: "ThalesGroup/fred",
          token: process.env.GITHUB_TOKEN,
        }),
        candidate: candidate.record,
        candidateRef,
        contract,
      });
      try {
        assert.deepEqual(
          attempt.record.execution,
          execution,
          "attempt execution differs from actual GitHub context",
        );
        const priorRefs = jsonEnvironment("RELEASE_PRIOR_ATTEMPT_REFS");
        assert(Array.isArray(priorRefs), "prior attempts must be an array");
        const priorAttempts = [];
        for (const ref of priorRefs) {
          validateArtifactRef(ref);
          const verified = await verifyRetainedAttempt({
            ref,
            artifact: await retrieveReleaseArtifact({
              ref,
              repository: "ThalesGroup/fred",
              token: process.env.GITHUB_TOKEN,
            }),
            candidate: candidate.record,
            candidateRef,
            contract,
          });
          priorAttempts.push(verified);
        }
        await assertCompleteCandidateAttemptHistory({
          candidate: candidate.record,
          candidateRef,
          candidateMetadata: candidate.artifactMetadata,
          candidateRunMetadata: candidate.artifactRunMetadata,
          historyLowerBound: await reviewedCoordinateHistoryStart(
            candidate.record,
            contract,
            run,
            { token: process.env.GITHUB_TOKEN },
          ),
          currentRef: attemptRef,
          priorRefs,
          token: process.env.GITHUB_TOKEN,
        });
        const terminalRefs = jsonEnvironment("RELEASE_PRIOR_TERMINAL_REFS");
        assert(
          Array.isArray(terminalRefs),
          "prior publishing terminals must be an array",
        );
        const verifiedTerminals = [];
        for (const ref of terminalRefs) {
          validateArtifactRef(ref);
          const matchingAttempt = priorAttempts.find(
            ({ ref: attemptRef }) =>
              attemptRef.runId === ref.runId &&
              attemptRef.runAttempt === ref.runAttempt &&
              attemptRef.sourceCommit === ref.sourceCommit,
          );
          assert(
            matchingAttempt,
            "terminal reference has no matching retained attempt",
          );
          verifiedTerminals.push(
            await verifyRetainedTerminal({
              ref,
              artifact: await retrieveReleaseArtifact({
                ref,
                repository: "ThalesGroup/fred",
                token: process.env.GITHUB_TOKEN,
              }),
              attempt: matchingAttempt,
              candidateRef,
              token: process.env.GITHUB_TOKEN,
            }),
          );
        }
        const result = await executeOrdinaryPublication({
          candidate: candidate.record,
          candidateRef,
          attempt: attempt.record,
          attemptRef,
          priorAttempts,
          verifiedTerminals,
          contract,
          archivePaths: candidate.archivePaths,
          verifyIntent: async ({ member }) => {
            const verified = await verifyRetainedAttempt({
              ref: attemptRef,
              artifact: await retrieveReleaseArtifact({
                ref: attemptRef,
                repository: "ThalesGroup/fred",
                token: process.env.GITHUB_TOKEN,
              }),
              candidate: candidate.record,
              candidateRef,
              contract,
            });
            try {
              assert.deepEqual(
                verified.record.commands.find(({ id }) => id === member.id),
                attempt.record.commands.find(({ id }) => id === member.id),
                `${member.id} retained pre-command intent differs`,
              );
              assert(
                verified.record.commands.some(({ id }) => id === member.id),
                `${member.id} has no package-specific retained intent`,
              );
            } finally {
              await verified.cleanup();
            }
          },
          onTerminal: async (record) => {
            const outputPath = process.env.RELEASE_TERMINAL_PATH;
            assert(outputPath, "RELEASE_TERMINAL_PATH is required");
            await mkdir(path.dirname(outputPath), { recursive: true });
            await writeFile(
              outputPath,
              `${JSON.stringify(record, null, 2)}\n`,
              { flag: "wx" },
            );
          },
          knownPublished: await loadKnownPublishedCoordinates(),
        });
        const outputPath = process.env.RELEASE_OUTCOME_PATH;
        assert(outputPath, "RELEASE_OUTCOME_PATH is required");
        await writeFile(outputPath, `${JSON.stringify(result, null, 2)}\n`, {
          flag: "wx",
        });
        process.stdout.write(`${JSON.stringify({ states: result.states })}\n`);
        await Promise.all(priorAttempts.map(({ cleanup }) => cleanup()));
        await Promise.all(verifiedTerminals.map(({ cleanup }) => cleanup()));
      } finally {
        await attempt.cleanup();
      }
    }
  } finally {
    await candidate.cleanup();
  }
}

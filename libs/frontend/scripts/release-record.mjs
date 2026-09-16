import assert from "node:assert/strict";
import { createHash } from "node:crypto";

import {
  baselineDigest,
  validateCompatibilityLedger,
} from "./compatibility-baselines.mjs";
import {
  assertPublishedDependencyReferences,
  validateReleaseContract,
} from "./release-contract.mjs";
import { verifyCandidateEvidence } from "./release-evidence.mjs";
import { assertDocumentSchema } from "./schema-validation.mjs";
import { orderReleaseMembers } from "./release-selection.mjs";
import path from "node:path";

const commitPattern = /^[a-f0-9]{40}$/;
const integrityPattern = /^sha512-[A-Za-z0-9+/]{86}==$/;
const policyDigestPattern = /^sha256-[A-Za-z0-9+/]{43}=$/;
const ledgerDigestPattern = /^sha256-[a-f0-9]{64}$/;
const policyFields = [
  "schemaVersion",
  "state",
  "registry",
  "distTag",
  "sourceBranch",
  "workflowFilename",
  "publishingEnvironment",
  "approvedBaselineDigest",
  "releaseToolchain",
  "applicationToolchain",
  "maintainerApproval",
  "expectedProvenance",
];

function digest(value) {
  return `sha256-${createHash("sha256").update(JSON.stringify(value)).digest("base64")}`;
}

function exactKeys(value, keys, label) {
  assert(
    value && typeof value === "object" && !Array.isArray(value),
    `${label} must be an object`,
  );
  assert.deepEqual(
    Object.keys(value).sort(),
    [...keys].sort(),
    `${label} keys`,
  );
}

export function releasePolicyDigest(contract) {
  validateReleaseContract(contract);
  return digest(
    Object.fromEntries(policyFields.map((key) => [key, contract[key]])),
  );
}

export function releaseRecordDigest(record) {
  validateReleaseRecord(record);
  return digest(record);
}

export function validateReleaseRecord(record) {
  assertDocumentSchema(
    record,
    path.resolve(import.meta.dirname, "../release/release-record.schema.json"),
    "release record",
  );
  assert.equal(record?.schemaVersion, 1, "unsupported release-record schema");
  if (record.kind === "candidate") {
    exactKeys(
      record,
      [
        "schemaVersion",
        "kind",
        "readiness",
        "sourceCommit",
        "transferOrigin",
        "selected",
        "compatibilityOnly",
        "policyDigest",
        "baselineDigest",
        "expectedProvenance",
        "observedToolchains",
        "gates",
        "archives",
        "manifestRanges",
      ],
      "candidate record",
    );
    assert(
      ["fixture", "incomplete", "complete"].includes(record.readiness),
      "invalid candidate readiness",
    );
    assert(
      commitPattern.test(record.sourceCommit),
      "candidate source commit invalid",
    );
    if (record.transferOrigin !== null) {
      exactKeys(
        record.transferOrigin,
        ["artifactName", "metadataDigest", "execution"],
        "candidate transfer origin",
      );
      assert(
        typeof record.transferOrigin.artifactName === "string" &&
          record.transferOrigin.artifactName.length > 0 &&
          policyDigestPattern.test(record.transferOrigin.metadataDigest),
        "candidate transfer artifact or metadata digest invalid",
      );
      exactKeys(
        record.transferOrigin.execution,
        ["provider", "repository", "workflow", "runId", "runAttempt"],
        "candidate transfer execution",
      );
      assert(
        ["github-actions", "local-rehearsal"].includes(
          record.transferOrigin.execution.provider,
        ) &&
          ["repository", "workflow", "runId", "runAttempt"].every(
            (field) => record.transferOrigin.execution[field],
          ),
        "candidate transfer execution incomplete",
      );
    }
    assert(
      Array.isArray(record.selected) && record.selected.length > 0,
      "candidate selection missing",
    );
    assert.equal(
      new Set(record.selected.map(({ id }) => id)).size,
      record.selected.length,
      "duplicate selected member",
    );
    assert(
      Array.isArray(record.compatibilityOnly),
      "compatibility selection missing",
    );
    assert.equal(
      new Set(record.compatibilityOnly.map(({ id }) => id)).size,
      record.compatibilityOnly.length,
      "duplicate compatibility member",
    );
    for (const member of record.compatibilityOnly) {
      exactKeys(
        member,
        ["id", "coordinate", "integrity"],
        "compatibility-only member",
      );
      assert(
        member.id &&
          /^@[a-z0-9-]+\/[a-z0-9-]+@\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$/.test(
            member.coordinate,
          ),
        "compatibility coordinate must be exact",
      );
      assert(
        integrityPattern.test(member.integrity),
        "compatibility integrity invalid",
      );
    }
    assert(
      record.selected.every(
        ({ id }) =>
          !record.compatibilityOnly.some((member) => member.id === id),
      ),
      "selected and compatibility-only members overlap",
    );
    assert(
      policyDigestPattern.test(record.policyDigest) &&
        ledgerDigestPattern.test(record.baselineDigest),
      "candidate policy or baseline digest missing",
    );
    assert(
      record.expectedProvenance?.repository &&
        record.expectedProvenance?.workflow &&
        record.expectedProvenance?.certificateIssuer,
      "candidate expected provenance missing",
    );
    exactKeys(
      record.observedToolchains,
      ["producer", "application"],
      "observed toolchains",
    );
    for (const [name, toolchain] of Object.entries(record.observedToolchains)) {
      assert(
        /^\d+\.\d+\.\d+$/.test(toolchain.node) &&
          /^\d+\.\d+\.\d+$/.test(toolchain.npm),
        `${name} observed toolchain is not exact`,
      );
    }
    exactKeys(
      record.archives,
      record.selected.map(({ id }) => id),
      "selected archive metadata",
    );
    for (const member of record.selected) {
      exactKeys(
        member,
        ["id", "coordinate", "builder", "validator", "consumer"],
        "selected member",
      );
      for (const field of ["id", "builder", "validator", "consumer"])
        assert(
          typeof member[field] === "string" && member[field].length > 0,
          `selected ${field} is missing`,
        );
      assert(
        /^@[a-z0-9-]+\/[a-z0-9-]+@\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$/.test(
          member.coordinate,
        ),
        "selected coordinate must be exact",
      );
      const archive = record.archives[member.id];
      exactKeys(
        archive,
        ["filename", "bytes", "integrity"],
        `${member.id} archive`,
      );
      assert(
        archive.filename.endsWith(".tgz") && !archive.filename.includes("/"),
        `${member.id} archive filename invalid`,
      );
      assert(
        Number.isSafeInteger(archive.bytes) && archive.bytes > 0,
        `${member.id} archive length invalid`,
      );
      assert(
        integrityPattern.test(archive.integrity),
        `${member.id} archive integrity invalid`,
      );
    }
    assert(
      record.gates && typeof record.gates === "object",
      "candidate gate evidence missing",
    );
    assert(
      record.manifestRanges && typeof record.manifestRanges === "object",
      "candidate manifest ranges missing",
    );
    exactKeys(
      record.manifestRanges,
      record.selected.map(({ id }) => id),
      "candidate manifest ranges",
    );
    for (const ranges of Object.values(record.manifestRanges)) {
      exactKeys(
        ranges,
        ["dependencies", "peerDependencies"],
        "manifest ranges",
      );
      assertPublishedDependencyReferences(ranges);
    }
    if (record.readiness === "complete")
      assert.equal(
        record.gates.archives?.validated,
        true,
        "complete candidate archive gate missing",
      );
  } else if (record.kind === "publishing-attempt") {
    exactKeys(
      record,
      [
        "schemaVersion",
        "kind",
        "readiness",
        "candidateDigest",
        "sourceCommit",
        "policyDigest",
        "baselineDigest",
        "candidateArtifact",
        "execution",
        "selected",
        "commands",
      ],
      "publishing attempt record",
    );
    assert(
      ["unpersisted", "persisted"].includes(record.readiness),
      "invalid attempt readiness",
    );
    assert(
      /^sha256-/.test(record.candidateDigest),
      "attempt candidate digest missing",
    );
    assert(
      commitPattern.test(record.sourceCommit) &&
        /^sha256-/.test(record.policyDigest) &&
        /^sha256-/.test(record.baselineDigest),
      "attempt source/policy/baseline binding missing",
    );
    if (record.readiness === "persisted") {
      exactKeys(
        record.candidateArtifact,
        [
          "artifactId",
          "runId",
          "runAttempt",
          "sourceCommit",
          "zipSha256",
          "recordDigest",
        ],
        "attempt candidate artifact",
      );
      assert(
        Number.isSafeInteger(record.candidateArtifact.artifactId) &&
          /^[a-f0-9]{64}$/.test(record.candidateArtifact.zipSha256),
        "persisted attempt candidate artifact identity missing",
      );
    }
    assertActualExecution(record.execution);
    assert(
      Array.isArray(record.selected) && record.selected.length > 0,
      "attempt selection missing",
    );
    assert.deepEqual(
      record.commands,
      record.selected.map(({ id, coordinate, integrity }) => ({
        id,
        coordinate,
        integrity,
        command: "npm publish",
        tag: "next",
        access: "public",
        provenance: true,
      })),
      "attempt command order differs from exact selected archives",
    );
  } else if (record.kind === "publishing-terminal") {
    exactKeys(
      record,
      [
        "schemaVersion",
        "kind",
        "readiness",
        "attemptDigest",
        "candidateDigest",
        "candidateArtifact",
        "execution",
        "passedBoundaries",
        "possiblyInvoked",
        "neverInvoked",
      ],
      "publishing terminal record",
    );
    assert.equal(
      record.readiness,
      "aborted",
      "terminal must describe an aborted publishing path",
    );
    assert(
      /^sha256-/.test(record.attemptDigest) &&
        /^sha256-/.test(record.candidateDigest),
      "terminal attempt/candidate binding is incomplete",
    );
    assertActualExecution(record.execution);
    assert(
      Array.isArray(record.passedBoundaries) &&
        Array.isArray(record.possiblyInvoked) &&
        Array.isArray(record.neverInvoked),
      "terminal boundaries are incomplete",
    );
    assert.equal(
      new Set([...record.passedBoundaries, ...record.neverInvoked]).size,
      record.passedBoundaries.length + record.neverInvoked.length,
      "terminal boundaries overlap or repeat",
    );
    assert(
      record.possiblyInvoked.every((id) =>
        record.passedBoundaries.includes(id),
      ),
      "terminal invocation is outside its passed boundary",
    );
    assert(
      record.neverInvoked.length,
      "terminal has no untouched package boundary",
    );
  } else if (record.kind === "publication-outcome") {
    exactKeys(
      record,
      [
        "schemaVersion",
        "kind",
        "readiness",
        "attemptDigest",
        "memberId",
        "coordinate",
        "integrity",
        "provenance",
      ],
      "publication outcome record",
    );
    assert(
      ["unverified", "verified"].includes(record.readiness),
      "invalid outcome readiness",
    );
    assert(
      /^sha256-/.test(record.attemptDigest) &&
        integrityPattern.test(record.integrity),
      "outcome digest or integrity invalid",
    );
    assert(
      record.memberId && record.coordinate && record.provenance,
      "outcome identity missing",
    );
  } else if (record.kind === "verification") {
    exactKeys(
      record,
      [
        "schemaVersion",
        "kind",
        "readiness",
        "candidateDigest",
        "execution",
        "outcomes",
        "gates",
      ],
      "verification record",
    );
    assert(
      ["controlled", "registry-verified"].includes(record.readiness),
      "invalid verification readiness",
    );
    assert(
      /^sha256-/.test(record.candidateDigest),
      "verification candidate digest missing",
    );
    assertActualExecution(record.execution);
    assert(
      Array.isArray(record.outcomes) && record.gates,
      "verification evidence missing",
    );
  } else throw new Error(`unsupported release record kind ${record.kind}`);
  return record;
}

function assertActualExecution(execution) {
  exactKeys(
    execution,
    [
      "repository",
      "workflow",
      "sourceCommit",
      "runId",
      "runAttempt",
      "signerIssuer",
    ],
    "actual execution",
  );
  assert(
    commitPattern.test(execution.sourceCommit),
    "actual execution commit invalid",
  );
  assert(
    execution.repository &&
      execution.workflow &&
      execution.runId &&
      execution.runAttempt &&
      execution.signerIssuer,
    "actual execution identity incomplete",
  );
}

// Existing candidate evidence remains the archive/gate authority; this model binds it to policy and baseline.
export async function candidateRecordFromEvidence({
  evidence,
  contract,
  ledger,
  selectedIds = evidence.selectedIds ?? Object.keys(evidence.packages),
  compatibilityOnly = [],
  archivePaths,
}) {
  validateReleaseContract(contract);
  assert.deepEqual(
    selectedIds,
    orderReleaseMembers(contract, selectedIds),
    "candidate record selection order differs from dependencies",
  );
  assert.deepEqual(
    selectedIds,
    evidence.selectedIds ?? Object.keys(evidence.packages),
    "candidate record selection differs from packed evidence",
  );
  assert.deepEqual(
    Object.keys(evidence.packages).sort(),
    [...selectedIds].sort(),
    "candidate record package set differs from packed evidence",
  );
  const requiredCompatibility =
    selectedIds.includes("ui") && !selectedIds.includes("designTokens")
      ? ["designTokens"]
      : [];
  assert.deepEqual(
    compatibilityOnly,
    requiredCompatibility,
    "candidate record compatibility selection differs from UI peer requirement",
  );
  validateCompatibilityLedger(ledger);
  assert.equal(
    baselineDigest(ledger),
    contract.approvedBaselineDigest,
    "compatibility ledger differs from approved policy digest",
  );
  // "complete" requires the existing byte/length/identity/gate verifier, not an evidence label.
  const archiveVerified = archivePaths
    ? await verifyCandidateEvidence(evidence, archivePaths, { contract })
    : false;
  const selected = selectedIds.map((id) => {
    const member = contract.inventory.members.find((entry) => entry.id === id);
    assert(member, `unregistered selected member ${id}`);
    const packageEvidence = evidence.packages[id];
    assert(packageEvidence, `missing ${id} packed evidence`);
    assert.equal(
      packageEvidence.coordinate,
      `${contract.packages[id].name}@${contract.packages[id].version}`,
      `${id} packed coordinate differs from manifest`,
    );
    return {
      id,
      coordinate: packageEvidence.coordinate,
      builder: member.builder,
      validator: member.validator,
      consumer: member.consumer,
    };
  });
  const archives = Object.fromEntries(
    selected.map(({ id }) => [
      id,
      {
        filename: evidence.packages[id].filename,
        bytes: evidence.packages[id].bytes,
        integrity: evidence.packages[id].integrity,
      },
    ]),
  );
  const record = {
    schemaVersion: 1,
    kind: "candidate",
    readiness:
      evidence.kind === "fixture-candidate-evidence" ||
      contract.state === "fixture"
        ? "fixture"
        : archiveVerified &&
            evidence.kind === "release-candidate-evidence" &&
            contract.state === "maintainer-confirmed"
          ? "complete"
          : "incomplete",
    sourceCommit: evidence.sourceCommit,
    transferOrigin: evidence.transfer
      ? {
          artifactName: evidence.transfer.artifactName,
          metadataDigest: evidence.transfer.metadataDigest,
          execution: evidence.transfer.execution,
        }
      : null,
    selected,
    compatibilityOnly: compatibilityOnly.map((id) => {
      const baseline = ledger.baselines.find((entry) => entry.memberId === id);
      assert(baseline, `missing approved compatibility baseline for ${id}`);
      return {
        id,
        coordinate: baseline.coordinate,
        integrity: baseline.expected.integrity,
      };
    }),
    policyDigest: releasePolicyDigest(contract),
    baselineDigest: `sha256-${baselineDigest(ledger)}`,
    expectedProvenance: contract.expectedProvenance,
    observedToolchains: {
      producer: evidence.producerToolchain,
      application: {
        node: evidence.applicationToolchain.node,
        npm: evidence.applicationToolchain.npm,
      },
    },
    gates: evidence.gates,
    archives,
    manifestRanges: Object.fromEntries(
      selected.map(({ id }) => [
        id,
        {
          dependencies:
            contract.packages[id].expectedManifest.dependencies ?? {},
          peerDependencies:
            contract.packages[id].expectedManifest.peerDependencies ?? {},
        },
      ]),
    ),
  };
  return validateReleaseRecord(record);
}

export function publishingAttemptModel({
  candidate,
  execution,
  candidateArtifact = null,
}) {
  validateReleaseRecord(candidate);
  assert.equal(candidate.kind, "candidate");
  const selected = candidate.selected.map(({ id, coordinate }) => ({
    id,
    coordinate,
    integrity: candidate.archives[id].integrity,
  }));
  return validateReleaseRecord({
    schemaVersion: 1,
    kind: "publishing-attempt",
    readiness: candidateArtifact ? "persisted" : "unpersisted",
    candidateDigest: releaseRecordDigest(candidate),
    sourceCommit: candidate.sourceCommit,
    policyDigest: candidate.policyDigest,
    baselineDigest: candidate.baselineDigest,
    candidateArtifact,
    execution,
    selected,
    commands: selected.map(({ id, coordinate, integrity }) => ({
      id,
      coordinate,
      integrity,
      command: "npm publish",
      tag: "next",
      access: "public",
      provenance: true,
    })),
  });
}

export function publishingTerminalModel({
  attempt,
  passedBoundaries,
  possiblyInvoked,
}) {
  validateReleaseRecord(attempt);
  assert.equal(attempt.kind, "publishing-attempt");
  const ordered = attempt.selected.map(({ id }) => id);
  assert.deepEqual(
    passedBoundaries,
    ordered.slice(0, passedBoundaries.length),
    "publishing terminal does not describe a serialized prefix",
  );
  assert(
    possiblyInvoked.every((id) => passedBoundaries.includes(id)),
    "terminal invocation differs from passed boundaries",
  );
  assert(
    passedBoundaries.length < ordered.length,
    "terminal has no untouched package",
  );
  return validateReleaseRecord({
    schemaVersion: 1,
    kind: "publishing-terminal",
    readiness: "aborted",
    attemptDigest: releaseRecordDigest(attempt),
    candidateDigest: attempt.candidateDigest,
    candidateArtifact: attempt.candidateArtifact,
    execution: attempt.execution,
    passedBoundaries,
    possiblyInvoked,
    neverInvoked: ordered.slice(passedBoundaries.length),
  });
}

export function publicationOutcomeModel({
  attempt,
  memberId,
  coordinate,
  integrity,
  provenance,
}) {
  validateReleaseRecord(attempt);
  assert.equal(attempt.kind, "publishing-attempt");
  assert(
    attempt.selected.some(
      (entry) =>
        entry.id === memberId &&
        entry.coordinate === coordinate &&
        entry.integrity === integrity,
    ),
    "outcome differs from attempt selection",
  );
  return validateReleaseRecord({
    schemaVersion: 1,
    kind: "publication-outcome",
    readiness: "unverified",
    attemptDigest: releaseRecordDigest(attempt),
    memberId,
    coordinate,
    integrity,
    provenance,
  });
}

export function verificationModel({
  candidate,
  execution,
  outcomes = [],
  gates = {},
}) {
  validateReleaseRecord(candidate);
  assert.equal(candidate.kind, "candidate");
  return validateReleaseRecord({
    schemaVersion: 1,
    kind: "verification",
    readiness: "controlled",
    candidateDigest: releaseRecordDigest(candidate),
    execution,
    outcomes: outcomes.map((record) => releaseRecordDigest(record)),
    gates,
  });
}

export function assertRecordAuthorizesPublication(
  record,
  { readback, candidate } = {},
) {
  validateReleaseRecord(record);
  assert.equal(
    record.kind,
    "publishing-attempt",
    "publication requires a distinct attempt record",
  );
  assert.equal(
    record.readiness,
    "persisted",
    "unpersisted model cannot authorize publication",
  );
  assert(
    readback && candidate,
    "durable attempt artifact readback and candidate are required",
  );
  assert.equal(
    readback.recordDigest,
    releaseRecordDigest(record),
    "attempt readback digest differs",
  );
  assert.equal(
    record.candidateDigest,
    releaseRecordDigest(candidate),
    "attempt candidate record differs",
  );
  assert.deepEqual(
    record.candidateArtifact,
    readback.candidateRef,
    "attempt candidate artifact differs from readback",
  );
  assert.equal(
    candidate.readiness,
    "complete",
    "publication requires a complete candidate",
  );
  return true;
}

export function assertRecordAuthorizesRegistrySuccess(
  record,
  { candidate, verifiedResult } = {},
) {
  validateReleaseRecord(record);
  assert.equal(
    record.kind,
    "verification",
    "registry success requires a distinct verification record",
  );
  assert.equal(
    record.readiness,
    "registry-verified",
    "controlled fixture evidence is not registry success",
  );
  assert(
    candidate && verifiedResult,
    "genuine registry result and retained candidate are required",
  );
  assert.equal(
    record.candidateDigest,
    releaseRecordDigest(candidate),
    "verification candidate digest differs",
  );
  assert.equal(
    verifiedResult.kind,
    "public-registry-verification",
    "controlled tooling is not registry success",
  );
  assert.deepEqual(
    verifiedResult.selectedIds,
    candidate.selected.map(({ id }) => id),
    "registry package selection differs",
  );
  for (const gate of [
    "exactRegistryArchives",
    "npmSignatures",
    "sigstoreProvenance",
    "cleanRegistryConsumers",
    "browserSmoke",
  ])
    assert.equal(record.gates[gate], true, `${gate} public gate missing`);
  assert.equal(
    record.gates.productionHostCompatibility,
    verifiedResult.selectedIds.includes("iframeSdk") ? true : "not-applicable",
    "production host gate must reflect SDK applicability",
  );
  assert.equal(
    record.outcomes.length,
    candidate.selected.length,
    "verified publication outcome set differs",
  );
  return true;
}

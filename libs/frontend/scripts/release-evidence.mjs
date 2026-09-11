import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  loadReleaseContract,
  packageRoles,
  validateReleaseContract,
} from "./release-contract.mjs";

const exactToolVersionPattern = /^\d+\.\d+\.\d+$/;

function assertApplicationToolchain(toolchain) {
  assert(toolchain && typeof toolchain === "object");
  assert.deepEqual(
    Object.keys(toolchain).sort(),
    ["isolation", "node", "npm", "source"],
    "application toolchain keys",
  );
  assert.equal(toolchain.isolation, "application-owned");
  assert.equal(typeof toolchain.source, "string");
  assert(
    toolchain.source.length > 0,
    "application toolchain source is required",
  );
  for (const field of ["node", "npm"])
    assert(
      exactToolVersionPattern.test(toolchain[field]),
      `application ${field} must be an exact version`,
    );
}

function assertCandidateGates(gates) {
  assert(
    gates && typeof gates === "object",
    "candidate gate evidence is required",
  );
  assert.equal(
    gates.archives?.validated,
    true,
    "archive validation evidence is required",
  );
  assert.equal(
    gates.archives?.reusedPackedBytes,
    true,
    "same-byte archive evidence is required",
  );
  for (const role of packageRoles)
    assert(
      gates.consumers?.[role] && typeof gates.consumers[role] === "object",
      `${role} consumer evidence is required`,
    );
  assert.equal(gates.browser?.dependencyInstallations, 0);
  assert.equal(gates.browser?.browserProvisioning, 0);
  assert.equal(gates.browser?.externalRequests, 0);
  assert.equal(
    typeof gates.host?.test,
    "string",
    "host gate evidence is required",
  );
  assert(gates.host.test.length > 0, "host gate test is required");
}

export async function sha512Integrity(filePath) {
  const bytes = await readFile(filePath);
  return `sha512-${createHash("sha512").update(bytes).digest("base64")}`;
}

export function releaseContractDigest(contract) {
  validateReleaseContract(contract);
  return `sha256-${createHash("sha256")
    .update(JSON.stringify(contract))
    .digest("base64")}`;
}

export async function createCandidateEvidence({
  contract,
  archives,
  sourceCommit,
  producerToolchain,
  applicationToolchain,
  gates,
  approved = false,
  createdAt = new Date().toISOString(),
}) {
  validateReleaseContract(contract);
  assertApplicationToolchain(applicationToolchain);
  if (approved) {
    assert.equal(
      contract.state,
      "maintainer-confirmed",
      "approved candidate evidence requires a maintainer-confirmed contract",
    );
  }
  assertCandidateGates(gates);
  assert.equal(
    archives.length,
    packageRoles.length,
    "all three archives are required",
  );
  const packages = {};
  for (const role of packageRoles) {
    const archive = archives.find((entry) => entry.role === role);
    assert(archive, `missing ${role} archive`);
    const expected = contract.packages[role];
    const integrity = await sha512Integrity(archive.path);
    packages[role] = {
      coordinate: `${expected.name}@${expected.version}`,
      filename: path.basename(archive.path),
      bytes: (await readFile(archive.path)).byteLength,
      integrity,
      expectedProvenance: {
        artifactDigest: integrity,
        repository: contract.expectedProvenance.repository,
        sourceCommit,
        workflow: contract.expectedProvenance.workflow,
        certificateIssuer: contract.expectedProvenance.certificateIssuer,
      },
    };
  }
  return {
    schemaVersion: 1,
    kind: approved
      ? "release-candidate-evidence"
      : "fixture-candidate-evidence",
    contractState: contract.state,
    contractDigest: releaseContractDigest(contract),
    createdAt,
    sourceCommit,
    producerToolchain,
    applicationToolchain,
    gates,
    registry: contract.registry,
    packages,
  };
}

export async function verifyCandidateEvidence(
  evidence,
  archivePaths,
  { contract } = {},
) {
  assert.equal(
    evidence.schemaVersion,
    1,
    "unsupported candidate evidence schema",
  );
  assert(
    ["fixture-candidate-evidence", "release-candidate-evidence"].includes(
      evidence.kind,
    ),
    "unsupported candidate evidence kind",
  );
  assertApplicationToolchain(evidence.applicationToolchain);
  assertCandidateGates(evidence.gates);
  if (contract) {
    assert.equal(
      evidence.contractDigest,
      releaseContractDigest(contract),
      "release contract differs from candidate evidence",
    );
    assert.equal(evidence.contractState, contract.state);
    assert.equal(evidence.registry, contract.registry);
    assert.deepEqual(evidence.producerToolchain, contract.releaseToolchain);
  }
  for (const role of packageRoles) {
    const recorded = evidence.packages?.[role];
    assert(recorded, `candidate evidence missing ${role}`);
    assert.equal(
      recorded.expectedProvenance?.artifactDigest,
      recorded.integrity,
      `${role} provenance digest is not bound to archive integrity`,
    );
    assert.equal(
      recorded.expectedProvenance?.sourceCommit,
      evidence.sourceCommit,
      `${role} provenance commit is not bound to the evidence commit`,
    );
    if (contract) {
      const expected = contract.packages[role];
      assert.equal(
        recorded.coordinate,
        `${expected.name}@${expected.version}`,
        `${role} evidence coordinate differs from release contract`,
      );
      assert.equal(
        recorded.expectedProvenance?.repository,
        contract.expectedProvenance.repository,
        `${role} evidence repository differs from release contract`,
      );
      assert.equal(
        recorded.expectedProvenance?.workflow,
        contract.expectedProvenance.workflow,
        `${role} evidence workflow differs from release contract`,
      );
      assert.equal(
        recorded.expectedProvenance?.certificateIssuer,
        contract.expectedProvenance.certificateIssuer,
        `${role} evidence certificate issuer differs from release contract`,
      );
    }
    const archivePath = archivePaths[role];
    assert(archivePath, `archive path missing ${role}`);
    assert.equal(
      path.basename(archivePath),
      recorded.filename,
      `${role} filename differs`,
    );
    assert.equal(
      await sha512Integrity(archivePath),
      recorded.integrity,
      `${role} bytes differ`,
    );
    assert.equal(
      (await readFile(archivePath)).byteLength,
      recorded.bytes,
      `${role} byte length differs`,
    );
  }
  return true;
}

function optionValue(name) {
  const index = process.argv.indexOf(name);
  return index === -1 ? undefined : process.argv[index + 1];
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const evidencePath = optionValue("--evidence");
  const contractPath = optionValue("--contract");
  assert(evidencePath, "--evidence is required");
  assert(contractPath, "--contract is required");
  const evidence = JSON.parse(
    await readFile(path.resolve(evidencePath), "utf8"),
  );
  const archivePaths = {
    designTokens: optionValue("--design-tokens"),
    ui: optionValue("--ui"),
    iframeSdk: optionValue("--iframe-sdk"),
  };
  for (const [role, archivePath] of Object.entries(archivePaths))
    assert(archivePath, `--${role} archive is required`);
  await verifyCandidateEvidence(evidence, archivePaths, {
    contract: await loadReleaseContract(contractPath),
  });
  process.stdout.write(
    `${JSON.stringify({ kind: "candidate-evidence-verification", archivePaths }, null, 2)}\n`,
  );
}

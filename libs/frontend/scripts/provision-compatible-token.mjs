import assert from "node:assert/strict";
import { cp, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { consumerCache } from "./provision-react-consumer.mjs";
import {
  baselineDigest,
  loadCompatibilityLedger,
  resolveUiTokenDependency,
} from "./compatibility-baselines.mjs";
import { loadReleaseContract } from "./release-contract.mjs";
import { sha512Integrity } from "./release-evidence.mjs";
import { run } from "./process.mjs";
import {
  assertProvenanceIdentity,
  resolveNpmRegistryPackage,
  verifyNpmPackageProvenance,
} from "./registry-verifier.mjs";

export const compatibilityRoot = path.resolve(
  import.meta.dirname,
  "../target/compatible-token",
);

// This is a network-capable provisioning operation, never an offline gate.
export async function provisionCompatibleToken({
  contract,
  ledger,
  cachePath = consumerCache,
  outputRoot = compatibilityRoot,
  resolvePackage = resolveNpmRegistryPackage,
  verifyProvenance = verifyNpmPackageProvenance,
  runCommand = run,
} = {}) {
  const dependency = resolveUiTokenDependency({
    contract,
    ledger,
    selectedIds: ["ui"],
  });
  const baseline = dependency.baseline;
  const baselineVersion = baseline.coordinate.slice(
    baseline.coordinate.lastIndexOf("@") + 1,
  );
  const registryContract = structuredClone(contract);
  registryContract.packages[baseline.memberId].version = baselineVersion;
  const temporaryRoot = await mkdtemp(
    path.join(os.tmpdir(), "fred-compatible-token-provision-"),
  );
  try {
    const candidate = {
      coordinate: baseline.coordinate,
      integrity: baseline.expected.integrity,
    };
    const registryPackage = await resolvePackage({
      coordinate: baseline.coordinate,
      registry: baseline.registry,
      root: temporaryRoot,
      role: baseline.memberId,
      contract: registryContract,
      evidence: { packages: { [baseline.memberId]: candidate } },
      expectedPackage: registryContract.packages[baseline.memberId],
      candidate,
    });
    assert.equal(
      `${registryPackage.metadata.name}@${registryPackage.metadata.version}`,
      baseline.coordinate,
      "baseline registry identity differs",
    );
    assert.equal(
      registryPackage.metadata.dist?.integrity,
      baseline.expected.integrity,
      "baseline registry metadata integrity differs",
    );
    assert.equal(
      await sha512Integrity(registryPackage.archivePath),
      baseline.expected.integrity,
      "baseline registry bytes differ",
    );
    const provenance = await verifyProvenance(registryPackage, {
      registry: baseline.registry,
      expectedProvenance: baseline.expected,
      certificateIssuer: baseline.expected.certificateIssuer,
    });
    assertProvenanceIdentity({
      cryptographicallyVerified: provenance.cryptographicallyVerified,
      actual: provenance.identity,
      expected: baseline.expected,
    });
    await runCommand(
      "npm",
      [
        "cache",
        "add",
        baseline.coordinate,
        "--cache",
        cachePath,
        "--registry",
        baseline.registry,
      ],
      { cwd: temporaryRoot },
    );
    await mkdir(outputRoot, { recursive: true });
    const archivePath = path.join(outputRoot, "design-tokens-baseline.tgz");
    await cp(registryPackage.archivePath, archivePath);
    const receipt = {
      kind: "compatible-token-provision",
      baselineDigest: baselineDigest(ledger),
      coordinate: baseline.coordinate,
      integrity: baseline.expected.integrity,
      provenance: provenance.identity,
      archiveFilename: path.basename(archivePath),
    };
    await writeFile(
      path.join(outputRoot, "receipt.json"),
      `${JSON.stringify(receipt, null, 2)}\n`,
    );
    return { archivePath, receipt, cachePath };
  } finally {
    await rm(temporaryRoot, { recursive: true, force: true });
  }
}

export async function assertCompatibleTokenProvision({
  contract,
  ledger,
  outputRoot = compatibilityRoot,
}) {
  const dependency = resolveUiTokenDependency({
    contract,
    ledger,
    selectedIds: ["ui"],
  });
  const baseline = dependency.baseline;
  const receiptBytes = await readFile(
    path.join(outputRoot, "receipt.json"),
    "utf8",
  ).catch((error) => {
    if (error.code === "ENOENT")
      throw new Error(
        `compatible token receipt is missing at ${outputRoot}; run make compatibility-provision before offline validation`,
        { cause: error },
      );
    throw error;
  });
  const receipt = JSON.parse(receiptBytes);
  assert.equal(receipt.kind, "compatible-token-provision");
  assert.equal(
    receipt.baselineDigest,
    baselineDigest(ledger),
    "prepared baseline ledger differs",
  );
  assert.equal(
    receipt.coordinate,
    baseline.coordinate,
    "prepared token coordinate differs",
  );
  assert.equal(
    receipt.integrity,
    baseline.expected.integrity,
    "prepared token integrity differs",
  );
  assert.deepEqual(
    {
      artifactDigest: receipt.provenance?.artifactDigest,
      repository: receipt.provenance?.repository,
      sourceCommit: receipt.provenance?.sourceCommit,
      workflow: receipt.provenance?.workflow,
    },
    {
      artifactDigest: baseline.expected.artifactDigest,
      repository: baseline.expected.repository,
      sourceCommit: baseline.expected.sourceCommit,
      workflow: baseline.expected.workflow,
    },
    "prepared token provenance differs",
  );
  assert.equal(receipt.archiveFilename, "design-tokens-baseline.tgz");
  const archivePath = path.join(outputRoot, receipt.archiveFilename);
  const actualIntegrity = await sha512Integrity(archivePath).catch((error) => {
    if (error.code === "ENOENT")
      throw new Error(
        `compatible token archive is missing at ${archivePath}; run make compatibility-provision before offline validation`,
        { cause: error },
      );
    throw error;
  });
  assert.equal(
    actualIntegrity,
    baseline.expected.integrity,
    "prepared token bytes differ",
  );
  return { archivePath, receipt };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const contract = await loadReleaseContract();
  const ledger = await loadCompatibilityLedger();
  process.stdout.write(
    `${JSON.stringify(await provisionCompatibleToken({ contract, ledger }), null, 2)}\n`,
  );
}

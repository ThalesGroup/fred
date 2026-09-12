import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { loadReleaseContract } from "../scripts/release-contract.mjs";
import {
  createCandidateEvidence,
  releaseContractDigest,
  verifyCandidateEvidence,
} from "../scripts/release-evidence.mjs";

const gates = {
  archives: { validated: true, reusedPackedBytes: true },
  consumers: { designTokens: {}, ui: {}, iframeSdk: {} },
  browser: {
    dependencyInstallations: 0,
    browserProvisioning: 0,
    externalRequests: 0,
  },
  host: { test: "fixture-host-test" },
};
const applicationToolchain = {
  source: "fixture",
  isolation: "application-owned",
  node: "22.13.0",
  npm: "10.9.2",
};

async function archives(context) {
  const root = await mkdtemp(path.join(os.tmpdir(), "fred-release-evidence-"));
  context.after(() => rm(root, { recursive: true, force: true }));
  const values = [];
  for (const role of ["designTokens", "ui", "iframeSdk"]) {
    const archivePath = path.join(root, `${role}.tgz`);
    await writeFile(archivePath, `${role} fixture bytes`);
    values.push({ role, path: archivePath });
  }
  return values;
}

test("fixture contracts produce only fixture evidence with bound provenance expectations", async (context) => {
  const contract = await loadReleaseContract();
  const values = await archives(context);
  const evidence = await createCandidateEvidence({
    contract,
    archives: values,
    sourceCommit: "fixture-commit",
    producerToolchain: { node: "24.21.0", npm: "11.19.0" },
    applicationToolchain,
    gates,
  });
  assert.equal(evidence.kind, "fixture-candidate-evidence");
  assert.equal(evidence.contractDigest, releaseContractDigest(contract));
  assert.equal(
    evidence.packages.ui.expectedProvenance.sourceCommit,
    "fixture-commit",
  );
  assert.equal(
    evidence.packages.ui.expectedProvenance.artifactDigest,
    evidence.packages.ui.integrity,
  );
  await assert.doesNotReject(
    verifyCandidateEvidence(
      evidence,
      Object.fromEntries(values.map((value) => [value.role, value.path])),
      { contract },
    ),
  );
  const changedContract = structuredClone(contract);
  changedContract.releaseToolchain.node = "24.21.1";
  await assert.rejects(
    verifyCandidateEvidence(
      evidence,
      Object.fromEntries(values.map((value) => [value.role, value.path])),
      { contract: changedContract },
    ),
    /release contract differs/,
  );
  await writeFile(values[1].path, "changed bytes");
  await assert.rejects(
    verifyCandidateEvidence(
      evidence,
      Object.fromEntries(values.map((value) => [value.role, value.path])),
    ),
    /bytes differ/,
  );
});

test("provisional values cannot produce approved release-candidate evidence", async (context) => {
  const contract = await loadReleaseContract();
  await assert.rejects(
    createCandidateEvidence({
      contract,
      archives: await archives(context),
      sourceCommit: "fixture-commit",
      producerToolchain: { node: "24.21.0", npm: "11.19.0" },
      applicationToolchain,
      gates,
      approved: true,
    }),
    /maintainer-confirmed/,
  );
});

test("candidate evidence requires exact application tooling and successful gate structures", async (context) => {
  const contract = await loadReleaseContract();
  const values = await archives(context);
  await assert.rejects(
    createCandidateEvidence({
      contract,
      archives: values,
      sourceCommit: "fixture-commit",
      producerToolchain: contract.releaseToolchain,
      applicationToolchain: {
        ...applicationToolchain,
        node: "22.x",
      },
      gates,
    }),
    /application node must be an exact version/,
  );
  await assert.rejects(
    createCandidateEvidence({
      contract,
      archives: values,
      sourceCommit: "fixture-commit",
      producerToolchain: contract.releaseToolchain,
      applicationToolchain,
      gates: { ...gates, archives: { validated: true } },
    }),
    /same-byte archive evidence is required/,
  );
});

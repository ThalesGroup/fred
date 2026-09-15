import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { readFileSync } from "node:fs";
import path from "node:path";
import semver from "semver";

import { sha512Integrity } from "./release-evidence.mjs";
import { verifyProvenanceAttestation } from "./registry-verifier.mjs";
import { assertDocumentSchema } from "./schema-validation.mjs";
import { validatePackageInventory } from "./release-inventory.mjs";
import { run } from "./process.mjs";

const sha512Pattern = /^sha512-[A-Za-z0-9+/]{86}==$/;
const sha256Pattern = /^[a-f0-9]{64}$/;
const commitPattern = /^[a-f0-9]{40}$/;
const ledgerFile = path.resolve(
  import.meta.dirname,
  "../release/compatibility-baselines.json",
);
const producerRoot = path.resolve(import.meta.dirname, "..");

export function baselineDigest(ledger) {
  validateCompatibilityLedger(ledger);
  return createHash("sha256").update(JSON.stringify(ledger)).digest("hex");
}

export function validateCompatibilityLedger(ledger) {
  assertDocumentSchema(
    ledger,
    path.resolve(
      import.meta.dirname,
      "../release/compatibility-baselines.schema.json",
    ),
    "compatibility ledger",
  );
  assert.deepEqual(
    Object.keys(ledger).sort(),
    ["$schema", "baselines", "schemaVersion"],
    "compatibility ledger keys",
  );
  assert.equal(ledger.$schema, "./compatibility-baselines.schema.json");
  assert.equal(ledger.schemaVersion, 1);
  assert(
    Array.isArray(ledger.baselines) && ledger.baselines.length > 0,
    "compatibility baselines missing",
  );
  const ids = new Set();
  for (const baseline of ledger.baselines) {
    assert.deepEqual(
      Object.keys(baseline).sort(),
      [
        "coordinate",
        "expected",
        "id",
        "memberId",
        "registry",
        "sourceReviewed",
        "verificationTrace",
      ],
      "baseline keys",
    );
    assert(!ids.has(baseline.id), "duplicate baseline ID");
    ids.add(baseline.id);
    assert.equal(
      baseline.sourceReviewed,
      true,
      "unreviewed baseline cannot authorize compatibility",
    );
    assert.equal(
      baseline.registry,
      "https://registry.npmjs.org/",
      "baseline registry differs",
    );
    assert(
      /^@[a-z0-9-]+\/[a-z0-9-]+@\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$/.test(
        baseline.coordinate,
      ),
      "baseline coordinate must be exact",
    );
    const inventory = validatePackageInventory(
      JSON.parse(
        readFileSync(
          path.join(producerRoot, "release/package-inventory.json"),
          "utf8",
        ),
      ),
    );
    const member = inventory.members.find(({ id }) => id === baseline.memberId);
    assert(member, "baseline member is unregistered");
    const manifest = JSON.parse(
      readFileSync(
        path.join(producerRoot, member.workspace, "package.json"),
        "utf8",
      ),
    );
    assert(
      baseline.coordinate.startsWith(`${manifest.name}@`),
      "baseline package name differs from registered manifest",
    );
    const expected = baseline.expected;
    assert.deepEqual(
      Object.keys(expected).sort(),
      [
        "artifactDigest",
        "certificateIssuer",
        "integrity",
        "repository",
        "sourceCommit",
        "workflow",
      ],
      "baseline expectation keys",
    );
    assert(
      sha512Pattern.test(expected.integrity),
      "baseline SHA-512 expectation missing or invalid",
    );
    assert.equal(
      expected.artifactDigest,
      expected.integrity,
      "baseline attested digest differs",
    );
    assert(
      commitPattern.test(expected.sourceCommit),
      "baseline source commit invalid",
    );
    assert.equal(
      expected.repository,
      "https://github.com/ThalesGroup/fred",
      "baseline repository differs",
    );
    assert(
      expected.workflow.startsWith(
        `${expected.repository}/.github/workflows/`,
      ) && expected.workflow.includes("@refs/heads/"),
      "baseline workflow expectation invalid",
    );
    assert.equal(
      expected.certificateIssuer,
      "https://token.actions.githubusercontent.com",
      "baseline signer issuer differs",
    );
    const trace = baseline.verificationTrace;
    assert.deepEqual(
      Object.keys(trace).sort(),
      [
        "artifactApiDigest",
        "artifactId",
        "artifactName",
        "artifactZipSha256",
        "historicalEvidenceSha256",
        "historicalGates",
        "oneTimeRegistryBytesMatched",
        "oneTimeSigstoreVerified",
        "runAttempt",
        "runId",
        "runUrl",
        "sourceCommit",
        "verifiedAt",
      ],
      "baseline verification trace keys",
    );
    assert(
      Number.isSafeInteger(trace.artifactId) && trace.artifactId > 0,
      "baseline artifact ID invalid",
    );
    assert(
      sha256Pattern.test(trace.artifactZipSha256),
      "baseline trace ZIP digest invalid",
    );
    assert.equal(
      trace.artifactApiDigest,
      `sha256:${trace.artifactZipSha256}`,
      "baseline artifact API digest differs",
    );
    assert(
      sha256Pattern.test(trace.historicalEvidenceSha256),
      "baseline historical evidence digest invalid",
    );
    assert(
      trace.artifactName &&
        trace.runUrl ===
          `https://github.com/ThalesGroup/fred/actions/runs/${trace.runId}`,
      "baseline artifact name or run URL invalid",
    );
    assert(
      /^\d{4}-\d{2}-\d{2}$/.test(trace.verifiedAt),
      "baseline verification date invalid",
    );
    assert(
      commitPattern.test(trace.sourceCommit),
      "baseline verifier commit invalid",
    );
    assert(
      trace.runId && trace.runAttempt,
      "baseline verifier execution missing",
    );
    assert.equal(
      trace.oneTimeRegistryBytesMatched,
      true,
      "baseline registry byte check missing",
    );
    assert.equal(
      trace.oneTimeSigstoreVerified,
      true,
      "baseline Sigstore check missing",
    );
    assert.deepEqual(
      new Set(trace.historicalGates),
      new Set([
        "exactRegistryArchives",
        "npmSignatures",
        "sigstoreProvenance",
        "cleanRegistryConsumers",
        "browserSmoke",
        "productionHostCompatibility",
      ]),
      "baseline historical gate trace incomplete",
    );
  }
  return ledger;
}

export async function loadCompatibilityLedger(filePath = ledgerFile) {
  return validateCompatibilityLedger(
    JSON.parse(await readFile(filePath, "utf8")),
  );
}

export function resolveUiTokenDependency({ contract, ledger, selectedIds }) {
  validateCompatibilityLedger(ledger);
  assert.equal(
    baselineDigest(ledger),
    contract.approvedBaselineDigest,
    "compatibility baseline differs from release policy",
  );
  const token = contract.packages.designTokens;
  const range =
    contract.packages.ui.expectedManifest.peerDependencies?.[token.name];
  assert(range, "UI token peer range is missing from the committed manifest");
  if (selectedIds.includes("designTokens")) {
    assert(
      semver.satisfies(token.version, range),
      `selected tokens ${token.version} do not satisfy UI peer ${range}`,
    );
    return { kind: "selected", coordinate: `${token.name}@${token.version}` };
  }
  const baseline = ledger.baselines.find(
    ({ memberId }) => memberId === "designTokens",
  );
  assert(baseline, "approved design-token baseline is missing");
  assert.equal(baseline.sourceReviewed, true, "unreviewed token baseline");
  assert.equal(
    baseline.registry,
    contract.registry,
    "token baseline registry differs from release policy",
  );
  const version = baseline.coordinate.slice(
    baseline.coordinate.lastIndexOf("@") + 1,
  );
  assert.equal(
    baseline.coordinate,
    `${token.name}@${version}`,
    "token baseline identity differs from committed manifest",
  );
  assert(
    semver.satisfies(version, range),
    `baseline tokens ${version} do not satisfy UI peer ${range}`,
  );
  return { kind: "compatibility", coordinate: baseline.coordinate, baseline };
}

// Historical ZIP is an import input only. Once committed, normal validation reads this ledger.
export async function verifyBaselineImport({
  baseline,
  historicalEvidence,
  historicalArtifact,
  metadata,
  tarballPath,
  attestation,
  verifyBundle,
}) {
  validateCompatibilityLedger({
    $schema: "./compatibility-baselines.schema.json",
    schemaVersion: 1,
    baselines: [baseline],
  });
  assert.equal(
    historicalArtifact?.id,
    baseline.verificationTrace.artifactId,
    "historical verification artifact ID differs",
  );
  assert.equal(
    historicalArtifact?.name,
    baseline.verificationTrace.artifactName,
    "historical verification artifact name differs",
  );
  assert.equal(
    historicalArtifact?.digest,
    baseline.verificationTrace.artifactApiDigest,
    "historical verification API digest differs",
  );
  const zipBytes = await readFile(historicalArtifact.zipPath);
  const actualZipSha256 = createHash("sha256").update(zipBytes).digest("hex");
  assert.equal(
    actualZipSha256,
    baseline.verificationTrace.artifactZipSha256,
    "historical verification ZIP digest differs",
  );
  const { stdout: evidenceText } = await run("unzip", [
    "-p",
    historicalArtifact.zipPath,
    "final-evidence.json",
  ]);
  assert.equal(
    createHash("sha256").update(evidenceText).digest("hex"),
    baseline.verificationTrace.historicalEvidenceSha256,
    "historical final evidence digest differs",
  );
  assert.deepEqual(
    JSON.parse(evidenceText),
    historicalEvidence,
    "historical final evidence was not extracted from the approved ZIP",
  );
  assert.equal(
    historicalEvidence.verificationExecution?.runId,
    baseline.verificationTrace.runId,
    "historical verification run differs",
  );
  assert.equal(
    historicalEvidence.verificationExecution?.runAttempt,
    baseline.verificationTrace.runAttempt,
    "historical verification attempt differs",
  );
  assert.equal(
    historicalEvidence.verificationExecution?.sourceCommit,
    baseline.verificationTrace.sourceCommit,
    "historical verification commit differs",
  );
  const historical = historicalEvidence.packages?.[baseline.memberId];
  assert.equal(
    historical?.coordinate,
    baseline.coordinate,
    "historical coordinate differs",
  );
  assert.equal(
    historical?.integrity,
    baseline.expected.integrity,
    "historical integrity differs",
  );
  for (const field of [
    "artifactDigest",
    "repository",
    "sourceCommit",
    "workflow",
  ])
    assert.equal(
      historical?.provenance?.[field],
      baseline.expected[field],
      `historical ${field} differs`,
    );
  for (const gate of baseline.verificationTrace.historicalGates)
    assert.equal(
      historicalEvidence.gates?.[gate],
      true,
      `historical ${gate} gate missing`,
    );
  return verifyBaselineAgainstRegistry({
    baseline,
    metadata,
    tarballPath,
    attestation,
    verifyBundle,
  });
}

export async function verifyBaselineAgainstRegistry({
  baseline,
  metadata,
  tarballPath,
  attestation,
  verifyBundle,
}) {
  assert.equal(
    `${metadata.name}@${metadata.version}`,
    baseline.coordinate,
    "registry baseline identity differs",
  );
  assert.equal(
    metadata.dist?.integrity,
    baseline.expected.integrity,
    "registry baseline metadata integrity differs",
  );
  const integrity = await sha512Integrity(tarballPath);
  assert.equal(
    integrity,
    baseline.expected.integrity,
    "registry baseline bytes differ",
  );
  const provenance = await verifyProvenanceAttestation(attestation, {
    verifyBundle,
    expectedWorkflow: baseline.expected.workflow,
    expectedRepository: baseline.expected.repository,
    certificateIssuer: baseline.expected.certificateIssuer,
  });
  assert.equal(
    provenance.cryptographicallyVerified,
    true,
    "baseline provenance is not verified",
  );
  for (const field of [
    "artifactDigest",
    "repository",
    "sourceCommit",
    "workflow",
  ])
    assert.equal(
      provenance.identity[field],
      baseline.expected[field],
      `baseline attested ${field} differs`,
    );
  return {
    coordinate: baseline.coordinate,
    integrity,
    cryptographicallyVerified: true,
  };
}

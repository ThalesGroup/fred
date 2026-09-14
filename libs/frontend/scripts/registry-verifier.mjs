import assert from "node:assert/strict";
import { verify as verifySignature } from "node:crypto";
import { fileURLToPath } from "node:url";
import { cp, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { verify as verifySigstoreBundle } from "sigstore";

import { assertRegistryConsumer } from "./dependency-boundaries.mjs";
import { runBrowserSmoke } from "./browser-smoke.mjs";
import { parameterizeConsumerSources } from "./consumer-contract.mjs";
import { runIframeSdkHostIntegration } from "./iframe-sdk-host-integration.mjs";
import { run } from "./process.mjs";
import {
  assertExactRegistryCoordinate,
  loadReleaseContract,
  packageRoles,
} from "./release-contract.mjs";
import {
  releaseContractDigest,
  sha512Integrity,
  verifyCandidateEvidence,
} from "./release-evidence.mjs";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const consumerFixtures = {
  designTokens: path.resolve(scriptDirectory, "../fixtures/neutral-consumer"),
  ui: path.resolve(scriptDirectory, "../fixtures/react-consumer"),
  iframeSdk: path.resolve(scriptDirectory, "../fixtures/iframe-sdk-consumer"),
};

const consumerRoles = {
  designTokens: ["designTokens"],
  ui: ["designTokens", "ui"],
  iframeSdk: ["iframeSdk"],
};

export function verifyFixtureSignature({ payload, signature, publicKey }) {
  return verifySignature(
    null,
    Buffer.isBuffer(payload) ? payload : Buffer.from(payload),
    publicKey,
    Buffer.from(signature, "base64"),
  );
}

export function assertProvenanceIdentity({
  cryptographicallyVerified,
  actual,
  expected,
}) {
  assert.equal(
    cryptographicallyVerified,
    true,
    "provenance cryptographic verification failed",
  );
  for (const field of [
    "artifactDigest",
    "repository",
    "sourceCommit",
    "workflow",
  ]) {
    assert(expected?.[field], `expected provenance ${field} is unconfirmed`);
    assert.equal(
      actual?.[field],
      expected[field],
      `provenance ${field} differs`,
    );
  }
  return true;
}

export function provenanceIdentityFromStatement(statement) {
  const subject = statement.subject?.[0];
  const subjectSha512 = subject?.digest?.sha512;
  const predicate = statement.predicate ?? {};
  const build = predicate.buildDefinition ?? {};
  const workflow = build.externalParameters?.workflow ?? {};
  const dependency = (build.resolvedDependencies ?? []).find(
    (entry) => entry.digest?.gitCommit,
  );
  return {
    artifactDigest: subjectSha512
      ? `sha512-${
          /^[0-9a-f]{128}$/i.test(subjectSha512)
            ? Buffer.from(subjectSha512, "hex").toString("base64")
            : subjectSha512
        }`
      : undefined,
    repository: workflow.repository,
    sourceCommit: dependency?.digest?.gitCommit,
    workflow:
      workflow.repository && workflow.path && workflow.ref
        ? `${workflow.repository}/${workflow.path}@${workflow.ref}`
        : undefined,
  };
}

export function statementFromDsseEnvelope(envelope) {
  assert.equal(envelope.payloadType, "application/vnd.in-toto+json");
  assert.equal(
    typeof envelope.payload,
    "string",
    "provenance payload is missing",
  );
  return JSON.parse(Buffer.from(envelope.payload, "base64").toString("utf8"));
}

export async function verifyProvenanceAttestation(
  document,
  {
    verifyBundle = verifySigstoreBundle,
    expectedWorkflow,
    certificateIssuer,
  } = {},
) {
  assert(expectedWorkflow, "expected provenance workflow is unconfirmed");
  assert(
    certificateIssuer,
    "expected provenance certificate issuer is unconfirmed",
  );
  const attestations = document?.attestations;
  assert(Array.isArray(attestations), "provenance attestations are missing");
  const provenance = attestations.find(({ predicateType }) =>
    /^https:\/\/slsa\.dev\/provenance\//.test(predicateType),
  );
  assert(provenance?.bundle, "SLSA provenance bundle is missing");
  await verifyBundle(provenance.bundle, {
    certificateIssuer,
    certificateIdentityURI: expectedWorkflow,
  });
  const statement = statementFromDsseEnvelope(provenance.bundle.dsseEnvelope);
  return {
    cryptographicallyVerified: true,
    identity: provenanceIdentityFromStatement(statement),
  };
}

export async function verifyRegistryTooling({
  contract,
  evidence,
  coordinates,
  resolvePackage,
  verifyPackageSignature,
  installConsumers,
}) {
  assert.equal(
    contract.state,
    "maintainer-confirmed",
    "public registry verification requires a maintainer-confirmed contract",
  );
  assert.equal(
    evidence.kind,
    "release-candidate-evidence",
    "public registry verification requires approved candidate evidence",
  );
  assert.equal(
    evidence.contractDigest,
    releaseContractDigest(contract),
    "release contract differs from approved candidate evidence",
  );
  const resolved = {};
  for (const role of packageRoles) {
    const expectedPackage = contract.packages[role];
    assertExactRegistryCoordinate(coordinates[role], expectedPackage);
    const candidate = evidence.packages[role];
    const registryPackage = await resolvePackage({
      coordinate: coordinates[role],
      registry: contract.registry,
    });
    assert.equal(
      registryPackage.integrity,
      candidate.integrity,
      `${role} registry integrity differs`,
    );
    const signatureResult = await verifyPackageSignature(registryPackage, {
      expectedProvenance: candidate.expectedProvenance,
      certificateIssuer: contract.expectedProvenance.certificateIssuer,
    });
    assertProvenanceIdentity({
      cryptographicallyVerified: signatureResult.cryptographicallyVerified,
      actual: signatureResult.identity,
      expected: candidate.expectedProvenance,
    });
    resolved[role] = registryPackage;
  }
  await verifyCandidateEvidence(
    evidence,
    Object.fromEntries(
      packageRoles.map((role) => [role, resolved[role].archivePath]),
    ),
    { contract },
  );
  await installConsumers({ contract, evidence, resolved });
  return {
    kind: "registry-verifier-tooling",
    registry: contract.registry,
    packages: Object.fromEntries(
      packageRoles.map((role) => [role, coordinates[role]]),
    ),
  };
}

export async function buildRegistryConsumers({
  contract,
  evidence,
  createRoot = () => mkdtemp(path.join(os.tmpdir(), "fred-registry-consumer-")),
  runCommand = run,
}) {
  const results = {};
  for (const role of packageRoles) {
    const root = await createRoot(role);
    await cp(consumerFixtures[role], root, { recursive: true });
    await parameterizeConsumerSources(root, contract, packageRoles);
    const manifestPath = path.join(root, "package.json");
    const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
    manifest.dependencies ??= {};
    for (const dependencyRole of consumerRoles[role]) {
      const selected = contract.packages[dependencyRole];
      manifest.dependencies[selected.name] = selected.version;
    }
    await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
    await runCommand(
      "npm",
      [
        "install",
        "--package-lock-only",
        "--ignore-scripts",
        "--registry",
        contract.registry,
      ],
      { cwd: root },
    );
    const lockfile = JSON.parse(
      await readFile(path.join(root, "package-lock.json"), "utf8"),
    );
    assertRegistryConsumer({
      manifest,
      lockfile,
      contract,
      evidence,
      roles: consumerRoles[role],
    });
    await runCommand(
      "npm",
      ["ci", "--ignore-scripts", "--registry", contract.registry],
      { cwd: root },
    );
    if (manifest.scripts?.typecheck)
      await runCommand("npm", ["run", "typecheck"], { cwd: root });
    await runCommand("npm", ["run", "build"], { cwd: root });
    results[role] = { root, roles: consumerRoles[role] };
  }
  return results;
}

export async function resolveNpmRegistryPackage({
  coordinate,
  registry,
  root,
  runCommand = run,
}) {
  const { stdout: metadataJson } = await runCommand(
    "npm",
    ["view", coordinate, "--json", "--registry", registry],
    { cwd: root },
  );
  const metadata = JSON.parse(metadataJson);
  const coordinateSeparator = coordinate.lastIndexOf("@");
  assert(coordinateSeparator > 0, `invalid registry coordinate ${coordinate}`);
  assert.equal(
    metadata.name,
    coordinate.slice(0, coordinateSeparator),
    `${coordinate} metadata name differs`,
  );
  assert.equal(
    metadata.version,
    coordinate.slice(coordinateSeparator + 1),
    `${coordinate} metadata version differs`,
  );
  const { stdout: packJson } = await runCommand(
    "npm",
    [
      "pack",
      coordinate,
      "--json",
      "--ignore-scripts",
      "--pack-destination",
      root,
      "--registry",
      registry,
    ],
    { cwd: root },
  );
  const [packed] = JSON.parse(packJson);
  const archivePath = path.join(root, packed.filename);
  const integrity = await sha512Integrity(archivePath);
  assert.equal(
    metadata.dist?.integrity,
    integrity,
    `${coordinate} metadata integrity differs`,
  );
  const advertisedAttestationUrl = metadata.dist?.attestations?.url;
  assert.equal(
    typeof advertisedAttestationUrl,
    "string",
    `${coordinate} attestation URL is missing`,
  );
  let advertised;
  try {
    advertised = new URL(advertisedAttestationUrl);
  } catch (error) {
    throw new Error(`${coordinate} attestation URL is malformed`, {
      cause: error,
    });
  }
  assert(
    ["http:", "https:"].includes(advertised.protocol),
    `${coordinate} attestation URL protocol is disallowed`,
  );
  assert.equal(
    advertised.username || advertised.password,
    "",
    `${coordinate} attestation URL credentials are disallowed`,
  );
  assert.equal(
    advertised.hash,
    "",
    `${coordinate} attestation URL fragment is disallowed`,
  );
  assert(
    advertised.pathname.startsWith("/-/npm/v1/attestations/"),
    `${coordinate} attestation URL path is disallowed`,
  );
  let attestedCoordinate;
  try {
    attestedCoordinate = decodeURIComponent(
      advertised.pathname.slice("/-/npm/v1/attestations/".length),
    );
  } catch (error) {
    throw new Error(`${coordinate} attestation URL is malformed`, {
      cause: error,
    });
  }
  assert.equal(
    attestedCoordinate,
    coordinate,
    `${coordinate} attestation URL coordinate differs`,
  );
  const provenanceUrl = new URL(advertised.pathname, registry);
  assert.equal(
    provenanceUrl.origin,
    new URL(registry).origin,
    `${coordinate} attestation URL escaped the approved registry`,
  );
  await writeFile(
    path.join(root, "package.json"),
    `${JSON.stringify({ private: true, dependencies: { [metadata.name]: metadata.version } })}\n`,
  );
  await runCommand(
    "npm",
    [
      "install",
      "--package-lock-only",
      "--ignore-scripts",
      "--registry",
      registry,
    ],
    { cwd: root },
  );
  return {
    coordinate,
    archivePath,
    integrity,
    metadata,
    provenanceUrl: provenanceUrl.href,
    root,
  };
}

export async function verifyNpmPackageProvenance(
  registryPackage,
  {
    registry,
    expectedProvenance,
    certificateIssuer,
    runCommand = run,
    fetchAttestation = fetch,
    verifyBundle = verifySigstoreBundle,
  },
) {
  await runCommand("npm", ["audit", "signatures", "--registry", registry], {
    cwd: registryPackage.root,
  });
  const attestationUrl = new URL(registryPackage.provenanceUrl);
  assert.equal(
    attestationUrl.origin,
    new URL(registry).origin,
    "provenance URL escaped the approved registry",
  );
  const response = await fetchAttestation(attestationUrl);
  assert.equal(
    response.ok,
    true,
    `provenance fetch failed: ${response.status}`,
  );
  return verifyProvenanceAttestation(await response.json(), {
    expectedWorkflow: expectedProvenance.workflow,
    certificateIssuer,
    verifyBundle,
  });
}

function optionValue(name) {
  const index = process.argv.indexOf(name);
  return index === -1 ? undefined : process.argv[index + 1];
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const contractPath = optionValue("--contract");
  const evidencePath = optionValue("--evidence");
  assert(contractPath, "--contract is required");
  assert(evidencePath, "--evidence is required");
  const contract = await loadReleaseContract(contractPath);
  const evidence = JSON.parse(
    await readFile(path.resolve(evidencePath), "utf8"),
  );
  const coordinates = {
    designTokens: optionValue("--design-tokens"),
    ui: optionValue("--ui"),
    iframeSdk: optionValue("--iframe-sdk"),
  };
  const roots = [];
  try {
    const result = await verifyRegistryTooling({
      contract,
      evidence,
      coordinates,
      resolvePackage: async ({ coordinate, registry }) => {
        const root = await mkdtemp(
          path.join(os.tmpdir(), "fred-registry-package-"),
        );
        roots.push(root);
        return resolveNpmRegistryPackage({ coordinate, registry, root });
      },
      verifyPackageSignature: async (
        registryPackage,
        { expectedProvenance, certificateIssuer },
      ) =>
        verifyNpmPackageProvenance(registryPackage, {
          registry: contract.registry,
          expectedProvenance,
          certificateIssuer,
        }),
      installConsumers: async ({ contract: selected, evidence: candidate }) => {
        const consumers = await buildRegistryConsumers({
          contract: selected,
          evidence: candidate,
          createRoot: async () => {
            const root = await mkdtemp(
              path.join(os.tmpdir(), "fred-registry-consumer-"),
            );
            roots.push(root);
            return root;
          },
        });
        await runBrowserSmoke({
          tokenOutput: path.join(consumers.designTokens.root, "dist"),
          reactOutput: path.join(consumers.ui.root, "dist"),
          iframeSdkOutput: path.join(consumers.iframeSdk.root, "dist"),
        });
        const sdk = selected.packages.iframeSdk;
        await runIframeSdkHostIntegration({
          contract: selected,
          sdkEntry: path.join(
            consumers.iframeSdk.root,
            "node_modules",
            ...sdk.name.split("/"),
            "dist/index.js",
          ),
        });
      },
    });
    process.stdout.write(
      `${JSON.stringify({ ...result, kind: "public-registry-verification" }, null, 2)}\n`,
    );
  } finally {
    await Promise.all(
      roots.map((root) => rm(root, { recursive: true, force: true })),
    );
  }
}

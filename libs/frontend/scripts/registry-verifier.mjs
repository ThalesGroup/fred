import assert from "node:assert/strict";
import { verify as verifySignature } from "node:crypto";
import { fileURLToPath } from "node:url";
import {
  cp,
  lstat,
  mkdtemp,
  readFile,
  realpath,
  rm,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { verify as verifySigstoreBundle } from "sigstore";

import { validateBootstrapRecoveryEvidence } from "./bootstrap-recovery-contract.mjs";
import { assertRegistryConsumer } from "./dependency-boundaries.mjs";
import {
  assertProvisionedChromium,
  runBrowserSmoke,
} from "./browser-smoke.mjs";
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
import { fetchExactPackageMetadata } from "./registry-metadata.mjs";

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

function canonicalRepository(value) {
  assert.equal(typeof value, "string", "provenance dependency URI is missing");
  const normalized = value.startsWith("git+") ? value.slice(4) : value;
  const repository = new URL(normalized);
  repository.hash = "";
  repository.search = "";
  repository.pathname = repository.pathname
    .replace(/@refs\/.*$/, "")
    .replace(/\.git\/?$/, "")
    .replace(/\/$/, "");
  return repository.href.replace(/\/$/, "");
}

export function provenanceIdentityFromStatement(statement, expectedRepository) {
  assert(expectedRepository, "expected provenance repository is unconfirmed");
  const subject = statement.subject?.[0];
  const subjectSha512 = subject?.digest?.sha512;
  const predicate = statement.predicate ?? {};
  const build = predicate.buildDefinition ?? {};
  const workflow = build.externalParameters?.workflow ?? {};
  const expected = canonicalRepository(expectedRepository);
  const dependencies = (build.resolvedDependencies ?? []).filter(
    (entry) =>
      entry.digest?.gitCommit && canonicalRepository(entry.uri) === expected,
  );
  assert.equal(
    dependencies.length,
    1,
    "provenance must identify exactly one source dependency for the expected repository",
  );
  const [dependency] = dependencies;
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
    expectedRepository,
    certificateIssuer,
  } = {},
) {
  assert(expectedWorkflow, "expected provenance workflow is unconfirmed");
  assert(expectedRepository, "expected provenance repository is unconfirmed");
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
    identity: provenanceIdentityFromStatement(statement, expectedRepository),
  };
}

export async function verifyRegistryTooling({
  contract,
  evidence,
  coordinates,
  resolvePackage,
  verifyPackageSignature,
  installConsumers,
  provenanceExpectations,
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
    assert(candidate, `candidate evidence missing ${role}`);
    const registryPackage = await resolvePackage({
      coordinate: coordinates[role],
      registry: contract.registry,
      role,
      contract,
      evidence,
      expectedPackage,
      candidate,
    });
    assert.equal(
      registryPackage.integrity,
      candidate.integrity,
      `${role} registry integrity differs`,
    );
    const expectedProvenance =
      provenanceExpectations?.[role] ?? candidate.expectedProvenance;
    const signatureResult = await verifyPackageSignature(registryPackage, {
      expectedProvenance,
      certificateIssuer: contract.expectedProvenance.certificateIssuer,
    });
    assertProvenanceIdentity({
      cryptographicallyVerified: signatureResult.cryptographicallyVerified,
      actual: signatureResult.identity,
      expected: expectedProvenance,
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
  role,
  contract,
  evidence,
  expectedPackage,
  candidate,
  runCommand = run,
  fetchMetadata = fetchExactPackageMetadata,
}) {
  assert.equal(
    new URL(registry).href,
    new URL(contract.registry).href,
    `${role} registry differs from the approved contract`,
  );
  assert.deepEqual(
    expectedPackage,
    contract.packages[role],
    `${role} expected package differs from the approved contract`,
  );
  assert.deepEqual(
    candidate,
    evidence.packages?.[role],
    `${role} candidate differs from approved evidence`,
  );
  assertExactRegistryCoordinate(coordinate, expectedPackage);
  assert.equal(
    candidate?.coordinate,
    coordinate,
    `${role} candidate coordinate differs`,
  );
  assert.match(
    candidate?.integrity ?? "",
    /^sha512-[A-Za-z0-9+/]+={0,2}$/,
    `${role} candidate integrity is missing or malformed`,
  );
  const metadata = await fetchMetadata({ coordinate, registry, candidate });
  assert(metadata, `${coordinate} exact version is absent from the registry`);
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
  assert.equal(
    integrity,
    candidate.integrity,
    `${role} downloaded registry integrity differs from candidate evidence`,
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
      "--no-audit",
      "--no-fund",
      "--registry",
      registry,
    ],
    { cwd: root },
  );
  const manifest = JSON.parse(
    await readFile(path.join(root, "package.json"), "utf8"),
  );
  const lockfile = JSON.parse(
    await readFile(path.join(root, "package-lock.json"), "utf8"),
  );
  assertRegistryConsumer({
    manifest,
    lockfile,
    contract,
    evidence,
    roles: [role],
  });
  await runCommand(
    "npm",
    [
      "ci",
      "--ignore-scripts",
      "--no-audit",
      "--no-fund",
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

export async function assertInstalledRegistryPackage({
  root,
  expectedPackage,
  runCommand = run,
}) {
  const { stdout } = await runCommand("npm", ["ls", "--all", "--json"], {
    cwd: root,
  });
  const installedTree = JSON.parse(stdout);
  const installed = installedTree.dependencies?.[expectedPackage.name];
  assert(
    installed,
    `${expectedPackage.name} is absent from the installed tree`,
  );
  assert.equal(
    installed.version,
    expectedPackage.version,
    `${expectedPackage.name} installed version differs`,
  );

  const packageRoot = path.join(
    root,
    "node_modules",
    ...expectedPackage.name.split("/"),
  );
  const packageStat = await lstat(packageRoot);
  assert.equal(
    packageStat.isSymbolicLink(),
    false,
    `${expectedPackage.name} installed package must not be a link`,
  );
  assert.equal(
    packageStat.isDirectory(),
    true,
    `${expectedPackage.name} installed package must be a directory`,
  );
  const [rootReal, packageReal] = await Promise.all([
    realpath(root),
    realpath(packageRoot),
  ]);
  const relative = path.relative(rootReal, packageReal);
  assert(
    relative && !relative.startsWith("..") && !path.isAbsolute(relative),
    `${expectedPackage.name} installed package escapes the disposable root`,
  );
  const installedManifest = JSON.parse(
    await readFile(path.join(packageReal, "package.json"), "utf8"),
  );
  assert.equal(
    installedManifest.name,
    expectedPackage.name,
    `${expectedPackage.name} installed manifest name differs`,
  );
  assert.equal(
    installedManifest.version,
    expectedPackage.version,
    `${expectedPackage.name} installed manifest version differs`,
  );
  return installedTree;
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
  await assertInstalledRegistryPackage({
    root: registryPackage.root,
    expectedPackage: {
      name: registryPackage.metadata.name,
      version: registryPackage.metadata.version,
    },
    runCommand,
  });
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
    expectedRepository: expectedProvenance.repository,
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
  const recoveryEvidencePath = optionValue("--recovery-evidence");
  const recoveryPlanPath = optionValue("--recovery-plan");
  let provenanceExpectations;
  if (recoveryEvidencePath || recoveryPlanPath) {
    assert(recoveryEvidencePath, "--recovery-evidence is required");
    assert(recoveryPlanPath, "--recovery-plan is required");
    const recoveryEvidence = JSON.parse(
      await readFile(path.resolve(recoveryEvidencePath), "utf8"),
    );
    const plan = JSON.parse(
      await readFile(path.resolve(recoveryPlanPath), "utf8"),
    );
    validateBootstrapRecoveryEvidence({
      contract,
      plan,
      evidence,
      recoveryEvidence,
      github: {
        actions: process.env.GITHUB_ACTIONS,
        repository: process.env.GITHUB_REPOSITORY,
        ref: process.env.GITHUB_REF,
        sha: process.env.GITHUB_SHA,
        workflowRef: process.env.GITHUB_WORKFLOW_REF,
        workflow: process.env.GITHUB_WORKFLOW,
        runId: process.env.GITHUB_RUN_ID,
        runAttempt: process.env.GITHUB_RUN_ATTEMPT,
      },
    });
    provenanceExpectations = recoveryEvidence.expectedProvenance;
  }
  const coordinates = {
    designTokens: optionValue("--design-tokens"),
    ui: optionValue("--ui"),
    iframeSdk: optionValue("--iframe-sdk"),
  };
  const roots = [];
  try {
    await assertProvisionedChromium();
    const result = await verifyRegistryTooling({
      contract,
      evidence,
      coordinates,
      resolvePackage: async ({
        coordinate,
        registry,
        role,
        contract: selected,
        evidence: candidateEvidence,
        expectedPackage,
        candidate,
      }) => {
        const root = await mkdtemp(
          path.join(os.tmpdir(), "fred-registry-package-"),
        );
        roots.push(root);
        return resolveNpmRegistryPackage({
          coordinate,
          registry,
          root,
          role,
          contract: selected,
          evidence: candidateEvidence,
          expectedPackage,
          candidate,
        });
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
      provenanceExpectations,
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

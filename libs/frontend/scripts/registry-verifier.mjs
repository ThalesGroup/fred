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
import {
  fetchExactPackageMetadata,
  waitForPackageMetadata,
} from "./registry-metadata.mjs";
import {
  loadCompatibilityLedger,
  resolveUiTokenDependency,
} from "./compatibility-baselines.mjs";
import {
  orderInventoryMembers,
  selectReleaseMembers,
  selectionOption,
} from "./release-selection.mjs";
import {
  retrieveReleaseArtifact,
  verifyRetainedCandidate,
  verifyRetainedAttempt,
} from "./release-artifact.mjs";
import { validateArtifactRef } from "./release-dispatch.mjs";
import {
  assertRecordAuthorizesRegistrySuccess,
  publicationOutcomeModel,
  releaseRecordDigest,
  validateReleaseRecord,
  verificationModel,
} from "./release-record.mjs";

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
    ...(["invocationRepository", "runId", "runAttempt"].some((field) =>
      Object.hasOwn(expected ?? {}, field),
    )
      ? ["invocationRepository", "runId", "runAttempt"]
      : []),
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

export function matchVerifiedPublishingAttempt({
  signature,
  expectedProvenance,
  publicationAttempts,
  memberId,
}) {
  const eligible = publicationAttempts.filter(({ record }) =>
    record.selected.some(({ id }) => id === memberId),
  );
  const matches = [];
  for (const attempt of eligible) {
    try {
      assertProvenanceIdentity({
        cryptographicallyVerified: signature.cryptographicallyVerified,
        actual: signature.identity,
        expected: {
          ...expectedProvenance,
          sourceCommit: attempt.record.execution.sourceCommit,
          invocationRepository: expectedProvenance.repository,
          runId: attempt.record.execution.runId,
          runAttempt: attempt.record.execution.runAttempt,
        },
      });
      matches.push(attempt);
    } catch {
      /* Another actual execution may have published this version. */
    }
  }
  assert(
    matches.length,
    "provenance does not match any retained actual publishing execution",
  );
  assert.equal(
    matches.length,
    1,
    "provenance attribution is ambiguous across retained attempts",
  );
  return matches[0];
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
  const invocationId = predicate.runDetails?.metadata?.invocationId;
  let invocation = {};
  if (invocationId !== undefined) {
    assert.equal(
      typeof invocationId,
      "string",
      "provenance invocation ID is malformed",
    );
    const url = new URL(invocationId);
    const match =
      /^\/([^/]+)\/([^/]+)\/actions\/runs\/([1-9][0-9]*)\/attempts\/([1-9][0-9]*)$/.exec(
        url.pathname,
      );
    assert(
      url.protocol === "https:" &&
        url.hostname === "github.com" &&
        !url.username &&
        !url.password &&
        !url.search &&
        !url.hash &&
        match,
      "provenance invocation ID is malformed",
    );
    const invocationRepository = `${url.origin}/${match[1]}/${match[2]}`;
    assert.equal(
      invocationId,
      `${invocationRepository}/actions/runs/${match[3]}/attempts/${match[4]}`,
      "provenance invocation ID is not canonical",
    );
    assert.equal(
      invocationRepository,
      expected,
      "provenance invocation repository differs",
    );
    invocation = {
      invocationRepository,
      runId: match[3],
      runAttempt: match[4],
    };
  }
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
    ...invocation,
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
  const provenanceEntries = attestations.filter(({ predicateType }) =>
    /^https:\/\/slsa\.dev\/provenance\//.test(predicateType),
  );
  assert.equal(
    provenanceEntries.length,
    1,
    "provenance must contain exactly one SLSA provenance entry",
  );
  const [provenance] = provenanceEntries;
  assert(provenance?.bundle, "SLSA provenance bundle is missing");
  await verifyBundle(provenance.bundle, {
    certificateIssuer,
    certificateIdentityURI: expectedWorkflow,
  });
  const statement = statementFromDsseEnvelope(provenance.bundle.dsseEnvelope);
  assert.equal(
    statement?._type,
    "https://in-toto.io/Statement/v1",
    "signed in-toto statement type differs",
  );
  assert.equal(
    statement?.predicateType,
    "https://slsa.dev/provenance/v1",
    "signed SLSA predicate differs",
  );
  assert.equal(
    statement.predicateType,
    provenance.predicateType,
    "signed SLSA predicate differs from registry metadata",
  );
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
  selectedIds = evidence.selectedIds ?? packageRoles,
  ledger,
  publicationAttempts,
}) {
  selectedIds = selectReleaseMembers(contract, selectedIds.join(","));
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
  assertSelectedRegistryInputs({
    inventory: contract.inventory,
    packages: contract.packages,
    selectedIds,
    coordinates,
    evidence,
  });
  const resolved = {};
  const verifiedPackages = {};
  let compatibilityOnly = [];
  if (selectedIds.includes("ui") && !selectedIds.includes("designTokens")) {
    assert(
      ledger,
      "UI-only registry verification requires the approved compatibility ledger",
    );
    const { baseline } = resolveUiTokenDependency({
      contract,
      ledger,
      selectedIds,
    });
    compatibilityOnly = [baseline];
  }
  for (const role of selectedIds) {
    const expectedPackage = contract.packages[role];
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
    const expectedProvenance = candidate.expectedProvenance;
    const signatureResult = await verifyPackageSignature(registryPackage, {
      expectedProvenance: publicationAttempts?.length
        ? {
            repository: expectedProvenance.repository,
            workflow: expectedProvenance.workflow,
          }
        : expectedProvenance,
      certificateIssuer: contract.expectedProvenance.certificateIssuer,
    });
    let matchedAttempt;
    if (publicationAttempts?.length) {
      matchedAttempt = matchVerifiedPublishingAttempt({
        signature: signatureResult,
        expectedProvenance,
        publicationAttempts,
        memberId: role,
      });
    } else
      assertProvenanceIdentity({
        cryptographicallyVerified: signatureResult.cryptographicallyVerified,
        actual: signatureResult.identity,
        expected: expectedProvenance,
      });
    resolved[role] = registryPackage;
    verifiedPackages[role] = {
      coordinate: coordinates[role],
      integrity: registryPackage.integrity,
      provenance: signatureResult.identity,
      ...(matchedAttempt
        ? { attemptDigest: releaseRecordDigest(matchedAttempt.record) }
        : {}),
    };
  }
  const consumerContract = structuredClone(contract);
  const verificationEvidence = {
    ...evidence,
    packages: { ...evidence.packages },
  };
  for (const baseline of compatibilityOnly) {
    const role = baseline.memberId;
    const version = baseline.coordinate.slice(
      baseline.coordinate.lastIndexOf("@") + 1,
    );
    consumerContract.packages[role].version = version;
    const expectedPackage = consumerContract.packages[role];
    const candidate = {
      coordinate: baseline.coordinate,
      integrity: baseline.expected.integrity,
    };
    const registryPackage = await resolvePackage({
      coordinate: baseline.coordinate,
      registry: baseline.registry,
      role,
      contract: consumerContract,
      evidence: { packages: { [role]: candidate } },
      expectedPackage,
      candidate,
    });
    assert.equal(
      registryPackage.integrity,
      baseline.expected.integrity,
      `${role} compatibility registry integrity differs`,
    );
    const signature = await verifyPackageSignature(registryPackage, {
      expectedProvenance: baseline.expected,
      certificateIssuer: baseline.expected.certificateIssuer,
    });
    assertProvenanceIdentity({
      cryptographicallyVerified: signature.cryptographicallyVerified,
      actual: signature.identity,
      expected: baseline.expected,
    });
    resolved[role] = registryPackage;
    verificationEvidence.packages[role] = candidate;
    verifiedPackages[role] = {
      coordinate: baseline.coordinate,
      integrity: registryPackage.integrity,
      provenance: signature.identity,
      compatibilityOnly: true,
    };
  }
  await verifyCandidateEvidence(
    evidence,
    Object.fromEntries(
      selectedIds.map((role) => [role, resolved[role].archivePath]),
    ),
    { contract },
  );
  await installConsumers({
    contract: consumerContract,
    evidence: verificationEvidence,
    resolved,
    selectedIds,
    compatibilityOnly: compatibilityOnly.map(({ memberId }) => memberId),
  });
  return {
    kind: "registry-verifier-tooling",
    registry: contract.registry,
    selectedIds,
    packages: verifiedPackages,
    gates: {
      exactRegistryArchives: true,
      npmSignatures: true,
      sigstoreProvenance: true,
      cleanRegistryConsumers: true,
      browserSmoke: true,
      productionHostCompatibility: applicableHostGate(selectedIds),
    },
  };
}

export function applicableHostGate(selectedIds) {
  return selectedIds.includes("iframeSdk") ? true : "not-applicable";
}

export function verificationEvidenceKind(retained) {
  return retained
    ? "public-registry-verification"
    : "controlled-selected-registry-tooling";
}

// Generic identity/selection boundary; a disposable profile can exercise this
// without bypassing the confirmed-contract and specialized archive gates.
export function assertSelectedRegistryInputs({
  inventory,
  packages,
  selectedIds,
  coordinates,
  evidence,
}) {
  orderInventoryMembers({ inventory, packages, selectedIds });
  assert.deepEqual(
    Object.keys(evidence.packages ?? {}).sort(),
    [...selectedIds].sort(),
    "registry candidate set differs from selection",
  );
  for (const id of selectedIds) {
    const expectedPackage = packages[id];
    assert(expectedPackage, `registry package ${id} is not registered`);
    assertExactRegistryCoordinate(coordinates[id], expectedPackage);
    assert.equal(
      evidence.packages[id]?.coordinate,
      coordinates[id],
      `${id} candidate coordinate differs`,
    );
    assert.match(
      evidence.packages[id]?.integrity ?? "",
      /^sha512-[A-Za-z0-9+/]+={0,2}$/,
      `${id} candidate integrity missing`,
    );
  }
  return true;
}

export async function buildRegistryConsumers({
  contract,
  evidence,
  createRoot = () => mkdtemp(path.join(os.tmpdir(), "fred-registry-consumer-")),
  runCommand = run,
  selectedIds = packageRoles,
  compatibilityOnly = [],
}) {
  const results = {};
  const consumerIds = [...new Set([...selectedIds, ...compatibilityOnly])];
  for (const role of consumerIds) {
    const root = await createRoot(role);
    await cp(consumerFixtures[role], root, { recursive: true });
    await parameterizeConsumerSources(root, contract, consumerIds);
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
  waitForPackageVisibility = waitForPackageMetadata,
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
  await waitForPackageVisibility({ coordinate, registry, candidate });
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
  const retiredOption = process.argv
    .slice(2)
    .find((option) => /^--(?:recovery|verification)-/.test(option));
  assert(
    !retiredOption,
    `${retiredOption} is retired; use --contract, --evidence, and exact package coordinates for generic verification`,
  );
  const contractPath = optionValue("--contract");
  const evidencePath = optionValue("--evidence");
  assert(contractPath, "--contract is required");
  const retained = process.argv.includes("--retained");
  if (!retained) assert(evidencePath, "--evidence is required");
  const contract = await loadReleaseContract(contractPath);
  const selection = selectionOption();
  const selectedIds = selectReleaseMembers(contract, selection);
  let candidateArtifact;
  let publicationAttempts = [];
  if (retained) {
    assert(
      process.env.GITHUB_TOKEN,
      "GITHUB_TOKEN is required for retained read-only verification",
    );
    const candidateRef = validateArtifactRef(
      JSON.parse(process.env.RELEASE_CANDIDATE_REF ?? "null"),
    );
    candidateArtifact = await verifyRetainedCandidate({
      ref: candidateRef,
      artifact: await retrieveReleaseArtifact({
        ref: candidateRef,
        repository: "ThalesGroup/fred",
        token: process.env.GITHUB_TOKEN,
      }),
      contract,
    });
    assert.deepEqual(
      candidateArtifact.selectedIds,
      selectedIds,
      "retained candidate selection differs from dispatch",
    );
    const attemptRefs = JSON.parse(
      process.env.RELEASE_PRIOR_ATTEMPT_REFS ?? "[]",
    );
    assert(
      Array.isArray(attemptRefs),
      "retained attempts must be a JSON array",
    );
    if (process.env.RELEASE_CURRENT_ATTEMPT_REF)
      attemptRefs.push(JSON.parse(process.env.RELEASE_CURRENT_ATTEMPT_REF));
    assert(
      attemptRefs.length > 0,
      "retained verification requires at least one persisted publishing attempt",
    );
    assert.equal(
      new Set(attemptRefs.map(({ artifactId }) => artifactId)).size,
      attemptRefs.length,
      "duplicate retained attempt reference",
    );
    for (const ref of attemptRefs) {
      validateArtifactRef(ref);
      publicationAttempts.push(
        await verifyRetainedAttempt({
          ref,
          artifact: await retrieveReleaseArtifact({
            ref,
            repository: "ThalesGroup/fred",
            token: process.env.GITHUB_TOKEN,
          }),
          candidate: candidateArtifact.record,
          candidateRef,
          contract,
        }),
      );
    }
  }
  const evidence = retained
    ? candidateArtifact.evidence
    : JSON.parse(await readFile(path.resolve(evidencePath), "utf8"));
  const coordinates = retained
    ? Object.fromEntries(
        candidateArtifact.record.selected.map(({ id, coordinate }) => [
          id,
          coordinate,
        ]),
      )
    : {
        designTokens: optionValue("--design-tokens"),
        ui: optionValue("--ui"),
        iframeSdk: optionValue("--iframe-sdk"),
      };
  const roots = [];
  const ledger =
    selectedIds.includes("ui") && !selectedIds.includes("designTokens")
      ? await loadCompatibilityLedger()
      : undefined;
  try {
    await assertProvisionedChromium();
    const result = await verifyRegistryTooling({
      contract,
      evidence,
      coordinates,
      selectedIds,
      ledger,
      publicationAttempts: retained ? publicationAttempts : undefined,
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
      installConsumers: async ({
        contract: selected,
        evidence: candidate,
        selectedIds: members,
        compatibilityOnly,
      }) => {
        const consumers = await buildRegistryConsumers({
          contract: selected,
          evidence: candidate,
          selectedIds: members,
          compatibilityOnly,
          createRoot: async () => {
            const root = await mkdtemp(
              path.join(os.tmpdir(), "fred-registry-consumer-"),
            );
            roots.push(root);
            return root;
          },
        });
        await runBrowserSmoke({
          tokenOutput: consumers.designTokens
            ? path.join(consumers.designTokens.root, "dist")
            : undefined,
          reactOutput: consumers.ui
            ? path.join(consumers.ui.root, "dist")
            : undefined,
          iframeSdkOutput: consumers.iframeSdk
            ? path.join(consumers.iframeSdk.root, "dist")
            : undefined,
          checks: [
            ...(consumers.designTokens ? ["tokens", "fonts"] : []),
            ...(consumers.ui ? ["ui"] : []),
            ...(consumers.iframeSdk ? ["iframeSdk"] : []),
          ],
        });
        if (consumers.iframeSdk) {
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
        }
      },
    });
    const finalEvidence = {
      ...result,
      kind: verificationEvidenceKind(retained),
    };
    if (retained) {
      const execution = {
        repository: process.env.GITHUB_REPOSITORY,
        workflow: contract.workflowFilename,
        sourceCommit: process.env.GITHUB_SHA,
        runId: process.env.GITHUB_RUN_ID,
        runAttempt: process.env.GITHUB_RUN_ATTEMPT,
        signerIssuer: contract.expectedProvenance.certificateIssuer,
      };
      assert.equal(
        process.env.GITHUB_REF,
        `refs/heads/${contract.sourceBranch}`,
        "verifier branch differs from release policy",
      );
      assert.equal(
        process.env.GITHUB_WORKFLOW_REF,
        `ThalesGroup/fred/.github/workflows/${contract.workflowFilename}@${process.env.GITHUB_REF}`,
        "verifier workflow differs from release policy",
      );
      const outcomes = selectedIds.map((id) => {
        const published = result.packages[id];
        const attempt = publicationAttempts.find(
          ({ record }) =>
            releaseRecordDigest(record) === published.attemptDigest,
        );
        assert(attempt, `${id} verified publishing attempt not found`);
        const outcome = publicationOutcomeModel({
          attempt: attempt.record,
          memberId: id,
          coordinate: published.coordinate,
          integrity: published.integrity,
          provenance: {
            ...published.provenance,
            cryptographicallyVerified: true,
          },
        });
        outcome.readiness = "verified";
        return validateReleaseRecord(outcome);
      });
      const record = verificationModel({
        candidate: candidateArtifact.record,
        execution,
        outcomes,
        gates: result.gates,
      });
      record.readiness = "registry-verified";
      validateReleaseRecord(record);
      Object.assign(finalEvidence, {
        candidateRef: validateArtifactRef(
          JSON.parse(process.env.RELEASE_CANDIDATE_REF),
        ),
        attemptRefs: publicationAttempts.map(({ ref }) => ref),
        verifierExecution: execution,
        record,
      });
      assertRecordAuthorizesRegistrySuccess(record, {
        candidate: candidateArtifact.record,
        verifiedResult: finalEvidence,
      });
    }
    const outputPath = optionValue("--output");
    if (outputPath)
      await writeFile(
        path.resolve(outputPath),
        `${JSON.stringify(finalEvidence, null, 2)}\n`,
        { flag: "wx" },
      );
    process.stdout.write(`${JSON.stringify(finalEvidence, null, 2)}\n`);
  } finally {
    await Promise.all(
      roots.map((root) => rm(root, { recursive: true, force: true })),
    );
    await candidateArtifact?.cleanup();
    await Promise.all(publicationAttempts.map(({ cleanup }) => cleanup()));
  }
}

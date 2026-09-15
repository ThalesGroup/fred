import assert from "node:assert/strict";
import { generateKeyPairSync, sign } from "node:crypto";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { loadReleaseContract } from "../scripts/release-contract.mjs";
import {
  releaseContractDigest,
  sha512Integrity,
} from "../scripts/release-evidence.mjs";
import {
  assertInstalledRegistryPackage,
  assertProvenanceIdentity,
  buildRegistryConsumers,
  provenanceIdentityFromStatement,
  resolveNpmRegistryPackage,
  statementFromDsseEnvelope,
  verifyFixtureSignature,
  verifyNpmPackageProvenance,
  verifyProvenanceAttestation,
  verifyRegistryTooling,
} from "../scripts/registry-verifier.mjs";
import { run } from "../scripts/process.mjs";

const fixtureContract = await loadReleaseContract();
const verifierCli = fileURLToPath(
  new URL("../scripts/registry-verifier.mjs", import.meta.url),
);

test("generic verifier loads in a fresh process and rejects retired CLI options", () => {
  const load = spawnSync(
    process.execPath,
    [
      "--input-type=module",
      "-e",
      `import(${JSON.stringify(new URL("../scripts/registry-verifier.mjs", import.meta.url).href)})`,
    ],
    {
      cwd: path.dirname(verifierCli),
      encoding: "utf8",
      timeout: 10000,
    },
  );
  assert.equal(load.status, 0, load.stderr);
  const generic = spawnSync(process.execPath, [verifierCli], {
    encoding: "utf8",
    timeout: 10000,
  });
  assert.match(generic.stderr, /--contract is required/);
  for (const retired of [
    "--recovery-evidence",
    "--recovery-plan",
    "--verification-plan",
    "--verification-inputs",
    "--recovery-artifact-zip",
    "--verification-future",
  ]) {
    const rejected = spawnSync(
      process.execPath,
      [verifierCli, retired, "unused"],
      {
        encoding: "utf8",
        timeout: 10000,
      },
    );
    assert.notEqual(rejected.status, 0);
    assert.match(rejected.stderr, /is retired/);
    assert.doesNotMatch(rejected.stderr, /--contract is required/);
  }
});

function expected(
  role = "ui",
  artifactDigest = `sha512-${role}`,
  contract = fixtureContract,
) {
  return {
    artifactDigest,
    repository: contract.expectedProvenance.repository,
    sourceCommit: "fixture-commit",
    workflow: contract.expectedProvenance.workflow,
  };
}

function confirmContract(contract) {
  contract.state = "maintainer-confirmed";
  contract.distTag = "next";
  contract.expectedProvenance.repository =
    "https://github.com/example/release-test";
  contract.expectedProvenance.workflow =
    "https://github.com/example/release-test/.github/workflows/release.yml@refs/heads/main";
  contract.maintainerApproval = {
    scopeOwner: "fred-oss",
    owners: {
      packageApi: "test-package-api-owner",
      sdkProtocol: "test-sdk-protocol-owner",
      release: "test-release-owner",
      npmPublishing: "test-npm-publishing-owner",
    },
    bootstrapIdentity: "test-bootstrap-identity",
    bootstrapAuthorityVerified: true,
    registryAccess: "public",
    publishingPolicy: "staged",
  };
  for (const entry of Object.values(contract.packages))
    entry.version = "0.1.0-alpha.1";
  contract.packages.ui.expectedManifest.peerDependencies[
    contract.packages.designTokens.name
  ] = "^0.1.0-alpha.1";
  return contract;
}

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

test("uses npm's dist.attestations.url metadata path for provenance", async (context) => {
  const root = await mkdtemp(path.join(os.tmpdir(), "fred-npm-metadata-"));
  context.after(() => rm(root, { recursive: true, force: true }));
  const selected = fixtureContract.packages.ui;
  const coordinate = `${selected.name}@${selected.version}`;
  const filename = "fred-ui-metadata-fixture.tgz";
  const archivePath = path.join(root, filename);
  await writeFile(archivePath, "npm metadata fixture archive");
  const integrity = await sha512Integrity(archivePath);
  const provenanceUrl =
    "https://registry.npmjs.org/-/npm/v1/attestations/%40fred-oss%2fui@0.1.0-alpha.1";
  const metadata = {
    name: selected.name,
    version: selected.version,
    dist: {
      integrity,
      attestations: {
        url: provenanceUrl,
        provenance: {
          predicateType: "https://slsa.dev/provenance/v1",
        },
      },
    },
  };
  const commands = [];
  const runCommand = async (command, args, options) => {
    commands.push([command, ...args]);
    if (args[0] === "view") return { stdout: JSON.stringify(metadata) };
    if (args[0] === "pack") return { stdout: JSON.stringify([{ filename }]) };
    if (args.includes("--package-lock-only")) {
      await writeFile(
        path.join(root, "package-lock.json"),
        `${JSON.stringify({
          lockfileVersion: 3,
          packages: {
            "": { dependencies: { [selected.name]: selected.version } },
            [`node_modules/${selected.name}`]: {
              version: selected.version,
              resolved: `${fixtureContract.registry}${selected.name}/-/ui.tgz`,
              integrity,
            },
          },
        })}\n`,
      );
    }
    if (args[0] === "ci") {
      const installedRoot = path.join(
        options.cwd,
        "node_modules",
        ...selected.name.split("/"),
      );
      await mkdir(installedRoot, { recursive: true });
      await writeFile(
        path.join(installedRoot, "package.json"),
        `${JSON.stringify({ name: selected.name, version: selected.version })}\n`,
      );
    }
    if (args[0] === "ls") {
      return {
        stdout: JSON.stringify({
          dependencies: {
            [selected.name]: { version: selected.version },
          },
        }),
      };
    }
    return { stdout: "" };
  };
  const candidate = { coordinate, integrity };
  const registryPackage = await resolveNpmRegistryPackage({
    coordinate,
    registry: fixtureContract.registry,
    root,
    role: "ui",
    contract: fixtureContract,
    evidence: { packages: { ui: candidate } },
    expectedPackage: selected,
    candidate,
    fetchMetadata: async () => metadata,
    waitForPackageVisibility: async () => metadata,
    runCommand,
  });
  assert.equal(registryPackage.provenanceUrl, provenanceUrl);

  const identity = expected("ui", integrity);
  const [workflowLocation, workflowRef] = identity.workflow.split("@");
  const statement = {
    subject: [{ digest: { sha512: integrity.slice("sha512-".length) } }],
    predicate: {
      buildDefinition: {
        externalParameters: {
          workflow: {
            repository: identity.repository,
            path: workflowLocation.slice(`${identity.repository}/`.length),
            ref: workflowRef,
          },
        },
        resolvedDependencies: [
          {
            uri: `git+${identity.repository}@refs/heads/swift`,
            digest: { gitCommit: identity.sourceCommit },
          },
        ],
      },
    },
  };
  const document = {
    attestations: [
      {
        predicateType: "https://slsa.dev/provenance/v1",
        bundle: {
          dsseEnvelope: {
            payloadType: "application/vnd.in-toto+json",
            payload: Buffer.from(JSON.stringify(statement)).toString("base64"),
          },
        },
      },
    ],
  };
  let fetched;
  const result = await verifyNpmPackageProvenance(registryPackage, {
    registry: fixtureContract.registry,
    expectedProvenance: identity,
    certificateIssuer: fixtureContract.expectedProvenance.certificateIssuer,
    runCommand,
    fetchAttestation: async (url) => {
      fetched = url;
      return { ok: true, status: 200, json: async () => document };
    },
    verifyBundle: async () => {},
  });
  assert.equal(fetched.href, provenanceUrl);
  assert.deepEqual(result.identity, identity);
  assert(commands.some(([, command]) => command === "audit"));
  const lockOnlyIndex = commands.findIndex((entry) =>
    entry.includes("--package-lock-only"),
  );
  const installIndex = commands.findIndex((entry) => entry.includes("ci"));
  const auditIndex = commands.findIndex((entry) => entry.includes("audit"));
  assert.notEqual(lockOnlyIndex, -1);
  assert.notEqual(installIndex, -1);
  assert.notEqual(auditIndex, -1);
  assert(lockOnlyIndex < installIndex && installIndex < auditIndex);
});

test("npm CLI distinguishes a lockfile-only graph from an installed dependency tree", async (context) => {
  const root = await mkdtemp(path.join(os.tmpdir(), "fred-installed-tree-"));
  context.after(() => rm(root, { recursive: true, force: true }));
  const packageRoot = path.join(root, "package");
  const consumerRoot = path.join(root, "consumer");
  const npmEnvironment = {
    ...process.env,
    npm_config_cache: path.join(root, "npm-cache"),
  };
  const npmRun = (command, args, options) =>
    run(command, args, { ...options, env: npmEnvironment });
  await Promise.all([mkdir(packageRoot), mkdir(consumerRoot)]);
  await writeFile(
    path.join(packageRoot, "package.json"),
    `${JSON.stringify({ name: "fred-installed-tree-fixture", version: "1.0.0" })}\n`,
  );
  const { stdout } = await npmRun(
    "npm",
    ["pack", packageRoot, "--json", "--pack-destination", consumerRoot],
    { cwd: root },
  );
  const [{ filename }] = JSON.parse(stdout);
  await writeFile(
    path.join(consumerRoot, "package.json"),
    `${JSON.stringify({
      private: true,
      dependencies: {
        "fred-installed-tree-fixture": `file:./${filename}`,
      },
    })}\n`,
  );
  await npmRun(
    "npm",
    ["install", "--package-lock-only", "--ignore-scripts", "--offline"],
    { cwd: consumerRoot },
  );
  const expectedPackage = {
    name: "fred-installed-tree-fixture",
    version: "1.0.0",
  };
  await assert.rejects(
    assertInstalledRegistryPackage({
      root: consumerRoot,
      expectedPackage,
      runCommand: npmRun,
    }),
    /missing: fred-installed-tree-fixture@/,
  );
  await npmRun("npm", ["ci", "--ignore-scripts", "--offline"], {
    cwd: consumerRoot,
  });
  const installed = await assertInstalledRegistryPackage({
    root: consumerRoot,
    expectedPackage,
    runCommand: npmRun,
  });
  assert.equal(
    installed.dependencies["fred-installed-tree-fixture"].version,
    "1.0.0",
  );
});

test("registry archive identity and candidate integrity fail before dependency installation", async (context) => {
  const root = await mkdtemp(
    path.join(os.tmpdir(), "fred-registry-integrity-"),
  );
  context.after(() => rm(root, { recursive: true, force: true }));
  const selected = fixtureContract.packages.ui;
  const coordinate = `${selected.name}@${selected.version}`;
  const filename = "ui.tgz";
  await writeFile(path.join(root, filename), "registry bytes");
  const integrity = await sha512Integrity(path.join(root, filename));
  const candidate = { coordinate, integrity: "sha512-dW5leHBlY3RlZA==" };
  const commands = [];
  await assert.rejects(
    resolveNpmRegistryPackage({
      coordinate,
      registry: fixtureContract.registry,
      root,
      role: "ui",
      contract: fixtureContract,
      evidence: { packages: { ui: candidate } },
      expectedPackage: selected,
      candidate,
      fetchMetadata: async () => ({
        name: selected.name,
        version: selected.version,
        dist: { integrity },
      }),
      waitForPackageVisibility: async () => {},
      runCommand: async (_command, args) => {
        commands.push(args);
        if (args[0] === "pack")
          return { stdout: JSON.stringify([{ filename }]) };
        return { stdout: "" };
      },
    }),
    /downloaded registry integrity differs from candidate evidence/,
  );
  assert.equal(
    commands.some((args) => args[0] === "install" || args[0] === "ci"),
    false,
  );
});

test("registry lock fallback fails before npm ci", async (context) => {
  const root = await mkdtemp(path.join(os.tmpdir(), "fred-registry-lock-"));
  context.after(() => rm(root, { recursive: true, force: true }));
  const selected = fixtureContract.packages.ui;
  const coordinate = `${selected.name}@${selected.version}`;
  const filename = "ui.tgz";
  const archivePath = path.join(root, filename);
  await writeFile(archivePath, "registry bytes");
  const integrity = await sha512Integrity(archivePath);
  const candidate = { coordinate, integrity };
  let installed = false;
  await assert.rejects(
    resolveNpmRegistryPackage({
      coordinate,
      registry: fixtureContract.registry,
      root,
      role: "ui",
      contract: fixtureContract,
      evidence: { packages: { ui: candidate } },
      expectedPackage: selected,
      candidate,
      fetchMetadata: async () => ({
        name: selected.name,
        version: selected.version,
        dist: {
          integrity,
          attestations: {
            url: `${fixtureContract.registry}-/npm/v1/attestations/${encodeURIComponent(coordinate)}`,
          },
        },
      }),
      waitForPackageVisibility: async () => {},
      runCommand: async (_command, args) => {
        if (args[0] === "pack")
          return { stdout: JSON.stringify([{ filename }]) };
        if (args.includes("--package-lock-only")) {
          await writeFile(
            path.join(root, "package-lock.json"),
            `${JSON.stringify({
              lockfileVersion: 3,
              packages: {
                "": { dependencies: { [selected.name]: selected.version } },
                [`node_modules/${selected.name}`]: {
                  version: selected.version,
                  resolved: "file:./ui.tgz",
                  integrity,
                },
              },
            })}\n`,
          );
        }
        if (args[0] === "ci") installed = true;
        return { stdout: "" };
      },
    }),
    /registry|local fallback/,
  );
  assert.equal(installed, false);
});

test("rejects missing, malformed, and disallowed npm attestation URLs", async (context) => {
  const selected = fixtureContract.packages.ui;
  const coordinate = `${selected.name}@${selected.version}`;
  for (const [label, attestations, error] of [
    ["missing", { provenance: {} }, /attestation URL is missing/],
    ["malformed", { url: "not a URL" }, /attestation URL is malformed/],
    [
      "protocol",
      { url: "file:///tmp/attestations" },
      /attestation URL protocol is disallowed/,
    ],
    [
      "path",
      { url: "https://registry.npmjs.org/unapproved/attestations" },
      /attestation URL path is disallowed/,
    ],
    [
      "credentials",
      {
        url: "https://user:secret@registry.npmjs.org/-/npm/v1/attestations/%40fred-oss%2fui@0.1.0-alpha.1",
      },
      /attestation URL credentials are disallowed/,
    ],
    [
      "fragment",
      {
        url: "https://registry.npmjs.org/-/npm/v1/attestations/%40fred-oss%2fui@0.1.0-alpha.1#other",
      },
      /attestation URL fragment is disallowed/,
    ],
    [
      "coordinate",
      {
        url: "https://registry.npmjs.org/-/npm/v1/attestations/%40fred-oss%2fother@0.1.0-alpha.1",
      },
      /attestation URL coordinate differs/,
    ],
  ]) {
    const root = await mkdtemp(
      path.join(os.tmpdir(), `fred-npm-metadata-${label}-`),
    );
    context.after(() => rm(root, { recursive: true, force: true }));
    const filename = `${label}.tgz`;
    const archivePath = path.join(root, filename);
    await writeFile(archivePath, `${label} archive`);
    const metadata = {
      name: selected.name,
      version: selected.version,
      dist: {
        integrity: await sha512Integrity(archivePath),
        attestations,
      },
    };
    const candidate = {
      coordinate,
      integrity: metadata.dist.integrity,
    };
    await assert.rejects(
      resolveNpmRegistryPackage({
        coordinate,
        registry: fixtureContract.registry,
        root,
        role: "ui",
        contract: fixtureContract,
        evidence: { packages: { ui: candidate } },
        expectedPackage: selected,
        candidate,
        fetchMetadata: async () => metadata,
        waitForPackageVisibility: async () => metadata,
        runCommand: async (_command, args) => {
          if (args[0] === "pack")
            return { stdout: JSON.stringify([{ filename }]) };
          return { stdout: "" };
        },
      }),
      error,
    );
  }
});

test("controlled provenance fixtures perform a real cryptographic signature check", () => {
  const { publicKey, privateKey } = generateKeyPairSync("ed25519");
  const payload = Buffer.from("signed provenance fixture");
  const signature = sign(null, payload, privateKey).toString("base64");
  assert.equal(verifyFixtureSignature({ payload, signature, publicKey }), true);
  assert.equal(
    verifyFixtureSignature({
      payload: Buffer.from("modified"),
      signature,
      publicKey,
    }),
    false,
  );
});

test("extracts identity from an in-toto SLSA statement", () => {
  const statement = {
    subject: [{ digest: { sha512: "ui" } }],
    predicate: {
      buildDefinition: {
        externalParameters: { workflow: { repository: expected().repository } },
        resolvedDependencies: [
          {
            uri: `git+${expected().repository}@refs/heads/fixture`,
            digest: { gitCommit: "fixture-commit" },
          },
        ],
      },
      runDetails: {
        builder: { id: "https://github.com/actions/runner/hosted" },
      },
    },
  };
  statement.predicate.buildDefinition.externalParameters.workflow.path =
    ".github/workflows/publish.yml";
  statement.predicate.buildDefinition.externalParameters.workflow.ref =
    "refs/heads/fixture";
  const envelope = {
    payloadType: "application/vnd.in-toto+json",
    payload: Buffer.from(JSON.stringify(statement)).toString("base64"),
  };
  assert.deepEqual(
    provenanceIdentityFromStatement(
      statementFromDsseEnvelope(envelope),
      expected().repository,
    ),
    expected(),
  );
});

test("selects the source commit only from the expected repository dependency", () => {
  const identity = expected();
  const statement = {
    subject: [{ digest: { sha512: "ui" } }],
    predicate: {
      buildDefinition: {
        externalParameters: {
          workflow: {
            repository: identity.repository,
            path: ".github/workflows/publish.yml",
            ref: "refs/heads/fixture",
          },
        },
        resolvedDependencies: [
          {
            uri: "https://example.invalid/unrelated.git",
            digest: { gitCommit: identity.sourceCommit },
          },
          {
            uri: `git+${identity.repository}@refs/heads/fixture`,
            digest: { gitCommit: "expected-repository-commit" },
          },
        ],
      },
    },
  };
  assert.equal(
    provenanceIdentityFromStatement(statement, identity.repository)
      .sourceCommit,
    "expected-repository-commit",
  );
  statement.predicate.buildDefinition.resolvedDependencies.push({
    uri: identity.repository,
    digest: { gitCommit: "ambiguous-commit" },
  });
  assert.throws(
    () => provenanceIdentityFromStatement(statement, identity.repository),
    /exactly one source dependency/,
  );
});

test("validly signed provenance still fails every wrong expected identity", async () => {
  const { publicKey, privateKey } = generateKeyPairSync("ed25519");
  async function verifiedIdentity(overrides = {}) {
    const identity = { ...expected(), ...overrides };
    const [workflowLocation, workflowRef] = identity.workflow.split("@");
    const workflowPath = workflowLocation.slice(
      `${identity.repository}/`.length,
    );
    const digest = identity.artifactDigest.slice("sha512-".length);
    const statement = {
      subject: [{ digest: { sha512: digest } }],
      predicate: {
        buildDefinition: {
          externalParameters: {
            workflow: {
              repository: identity.repository,
              path: workflowPath,
              ref: workflowRef,
            },
          },
          resolvedDependencies: [
            {
              uri: expected().repository,
              digest: { gitCommit: identity.sourceCommit },
            },
          ],
        },
      },
    };
    const payload = Buffer.from(JSON.stringify(statement)).toString("base64");
    const signature = sign(null, Buffer.from(payload), privateKey).toString(
      "base64",
    );
    return verifyProvenanceAttestation(
      {
        attestations: [
          {
            predicateType: "https://slsa.dev/provenance/v1",
            bundle: {
              dsseEnvelope: {
                payloadType: "application/vnd.in-toto+json",
                payload,
                signatures: [{ sig: signature }],
              },
            },
          },
        ],
      },
      {
        expectedWorkflow: fixtureContract.expectedProvenance.workflow,
        expectedRepository: fixtureContract.expectedProvenance.repository,
        certificateIssuer: fixtureContract.expectedProvenance.certificateIssuer,
        verifyBundle: async (bundle, options) => {
          assert.deepEqual(options, {
            certificateIssuer:
              fixtureContract.expectedProvenance.certificateIssuer,
            certificateIdentityURI: fixtureContract.expectedProvenance.workflow,
          });
          assert.equal(
            verifyFixtureSignature({
              payload: bundle.dsseEnvelope.payload,
              signature: bundle.dsseEnvelope.signatures[0].sig,
              publicKey,
            }),
            true,
          );
        },
      },
    );
  }

  for (const [field, value] of Object.entries({
    artifactDigest: "sha512-other",
    repository: "https://example.invalid/other-repository",
    sourceCommit: "other-commit",
    workflow:
      "https://example.invalid/fred-release-fixture/.github/workflows/other.yml@refs/heads/fixture",
  })) {
    const result = await verifiedIdentity({ [field]: value });
    assert.equal(result.cryptographicallyVerified, true);
    assert.throws(
      () =>
        assertProvenanceIdentity({
          cryptographicallyVerified: result.cryptographicallyVerified,
          actual: result.identity,
          expected: expected(),
        }),
      new RegExp(`${field} differs`),
    );
  }
});

test("provenance verification requires an explicit signer certificate policy", async () => {
  await assert.rejects(
    verifyProvenanceAttestation({ attestations: [] }),
    /expected provenance workflow is unconfirmed/,
  );
  await assert.rejects(
    verifyProvenanceAttestation(
      { attestations: [] },
      {
        expectedWorkflow: fixtureContract.expectedProvenance.workflow,
        expectedRepository: fixtureContract.expectedProvenance.repository,
      },
    ),
    /expected provenance certificate issuer is unconfirmed/,
  );
});

test("signature validity and expected release identity are separate gates", () => {
  assert.throws(
    () =>
      assertProvenanceIdentity({
        cryptographicallyVerified: false,
        actual: expected(),
        expected: expected(),
      }),
    /cryptographic verification failed/,
  );
  for (const field of [
    "artifactDigest",
    "repository",
    "sourceCommit",
    "workflow",
  ]) {
    const actual = { ...expected(), [field]: `unexpected-${field}` };
    assert.throws(
      () =>
        assertProvenanceIdentity({
          cryptographicallyVerified: true,
          actual,
          expected: expected(),
        }),
      new RegExp(`${field} differs`),
    );
  }
  assert.throws(
    () =>
      assertProvenanceIdentity({
        cryptographicallyVerified: true,
        actual: expected(),
        expected: { ...expected(), workflow: null },
      }),
    /workflow is unconfirmed/,
  );
});

test("controlled registry orchestration cannot use fixture evidence as public proof", async () => {
  const coordinates = Object.fromEntries(
    Object.entries(fixtureContract.packages).map(([role, value]) => [
      role,
      `${value.name}@${value.version}`,
    ]),
  );
  await assert.rejects(
    verifyRegistryTooling({
      contract: fixtureContract,
      evidence: { kind: "fixture-candidate-evidence" },
      coordinates,
    }),
    /maintainer-confirmed/,
  );
});

test("controlled registry orchestration verifies identity before consumers", async (context) => {
  const contract = confirmContract(structuredClone(fixtureContract));
  const root = await mkdtemp(path.join(os.tmpdir(), "fred-registry-tooling-"));
  context.after(() => rm(root, { recursive: true, force: true }));
  const coordinates = {};
  const packages = {};
  for (const [role, value] of Object.entries(contract.packages)) {
    const archivePath = path.join(root, `${role}.tgz`);
    await writeFile(archivePath, `${role} registry fixture`);
    const integrity = await sha512Integrity(archivePath);
    coordinates[role] = `${value.name}@${value.version}`;
    packages[role] = {
      coordinate: coordinates[role],
      filename: path.basename(archivePath),
      bytes: (await readFile(archivePath)).byteLength,
      integrity,
      expectedProvenance: {
        ...expected(role, integrity, contract),
        certificateIssuer: contract.expectedProvenance.certificateIssuer,
      },
      archivePath,
    };
  }
  let installed = false;
  const result = await verifyRegistryTooling({
    contract,
    evidence: {
      kind: "release-candidate-evidence",
      schemaVersion: 1,
      contractState: contract.state,
      contractDigest: releaseContractDigest(contract),
      producerToolchain: contract.releaseToolchain,
      applicationToolchain,
      sourceCommit: "fixture-commit",
      registry: contract.registry,
      gates,
      packages,
    },
    coordinates,
    resolvePackage: async ({ coordinate }) => {
      const role = Object.entries(coordinates).find(
        ([, value]) => value === coordinate,
      )[0];
      return {
        coordinate,
        integrity: packages[role].integrity,
        archivePath: packages[role].archivePath,
        role,
      };
    },
    verifyPackageSignature: async (
      { role },
      { expectedProvenance, certificateIssuer },
    ) => {
      assert.equal(expectedProvenance, packages[role].expectedProvenance);
      assert.equal(
        certificateIssuer,
        contract.expectedProvenance.certificateIssuer,
      );
      return {
        cryptographicallyVerified: true,
        identity: packages[role].expectedProvenance,
      };
    },
    installConsumers: async () => {
      installed = true;
    },
  });
  assert.equal(installed, true);
  assert.equal(result.kind, "registry-verifier-tooling");
});

test("registry consumer tooling builds three clean exact-version fixtures", async () => {
  const contract = confirmContract(structuredClone(fixtureContract));
  const packages = Object.fromEntries(
    Object.entries(contract.packages).map(([role, value]) => [
      role,
      {
        coordinate: `${value.name}@${value.version}`,
        integrity: expected(role).artifactDigest,
      },
    ]),
  );
  const roots = [];
  const commands = [];
  try {
    const results = await buildRegistryConsumers({
      contract,
      evidence: { kind: "release-candidate-evidence", packages },
      createRoot: async () => {
        const root = await mkdtemp(
          path.join(os.tmpdir(), "fred-registry-consumer-test-"),
        );
        roots.push(root);
        return root;
      },
      runCommand: async (command, args, options) => {
        commands.push([command, ...args]);
        if (args.includes("--package-lock-only")) {
          const manifest = JSON.parse(
            await readFile(path.join(options.cwd, "package.json"), "utf8"),
          );
          const lockPackages = {
            "": { dependencies: manifest.dependencies },
          };
          for (const [role, selected] of Object.entries(contract.packages)) {
            if (!(selected.name in manifest.dependencies)) continue;
            lockPackages[`node_modules/${selected.name}`] = {
              version: selected.version,
              resolved: `${contract.registry}${selected.name}/-/${role}.tgz`,
              integrity: packages[role].integrity,
            };
          }
          await writeFile(
            path.join(options.cwd, "package-lock.json"),
            `${JSON.stringify({ lockfileVersion: 3, packages: lockPackages })}\n`,
          );
        }
        return { stdout: "", stderr: "" };
      },
    });
    assert.deepEqual(Object.keys(results), ["designTokens", "ui", "iframeSdk"]);
    assert.equal(
      commands.filter((entry) => entry.includes("--package-lock-only")).length,
      3,
    );
    assert.equal(
      commands.filter((entry) => entry.includes("typecheck")).length,
      2,
    );
    assert.equal(commands.filter((entry) => entry.includes("build")).length, 3);
  } finally {
    await Promise.all(
      roots.map((root) => rm(root, { recursive: true, force: true })),
    );
  }
});

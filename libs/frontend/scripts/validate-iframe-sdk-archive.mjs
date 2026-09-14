import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { lstat, mkdtemp, readFile, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  assertArchiveEntriesSafe,
  assertNoArchiveLinks,
  dependencyEntries,
  listArchiveFiles,
} from "./archive-safety.mjs";
import {
  IFRAME_SDK_CANONICAL_SOURCE_PATH,
  IFRAME_SDK_SOURCE_PATHS,
} from "./package-inputs.mjs";
import { inspectModuleReferences } from "./module-references.mjs";
import { run } from "./process.mjs";
import {
  assertExpectedManifest,
  loadReleaseContract,
  packageContract,
} from "./release-contract.mjs";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const repositoryRoot = path.resolve(scriptDirectory, "../../..");
const approvedFredLicenseHash =
  "c4f0580f5e58f572f41c1985ac9920c227c166f09d25cba1a01ace86409c6e5c";

export const expectedIframeSdkArchiveFiles = [
  "LICENSE",
  "README.md",
  "build-evidence.json",
  "dist/index.js",
  "dist/protocol.js",
  "dist/types/.generated/applicationProtocol.d.ts",
  "dist/types/src/index.d.ts",
  "package.json",
];

const expectedExports = {
  ".": { types: "./dist/types/src/index.d.ts", import: "./dist/index.js" },
  "./protocol": {
    types: "./dist/types/.generated/applicationProtocol.d.ts",
    import: "./dist/protocol.js",
  },
};

function sha256(content) {
  return createHash("sha256").update(content).digest("hex");
}

async function isRegularFile(candidate) {
  return lstat(candidate).then(
    (entry) => entry.isFile(),
    () => false,
  );
}

function confinedTarget(packageRoot, owner, reference) {
  const resolved = path.resolve(
    path.dirname(path.join(packageRoot, owner)),
    reference,
  );
  const relative = path.relative(packageRoot, resolved);
  assert(
    !relative.startsWith("..") && !path.isAbsolute(relative),
    `${owner} has escaping reference ${reference}`,
  );
  return resolved;
}

async function executableTarget(resolved) {
  return [".js", ".mjs", ".cjs"].includes(path.extname(resolved)) &&
    (await isRegularFile(resolved))
    ? resolved
    : null;
}

async function declarationTarget(resolved) {
  const candidates = path.extname(resolved)
    ? [resolved, resolved.replace(/\.(?:tsx?|jsx?|mjs|cjs)$/, ".d.ts")]
    : [`${resolved}.d.ts`, path.join(resolved, "index.d.ts")];
  for (const candidate of candidates) {
    if (candidate.endsWith(".d.ts") && (await isRegularFile(candidate)))
      return candidate;
  }
  return null;
}

function assertNoForbiddenReferences(relativePath, content) {
  for (const forbidden of [
    /(?:workspace|file|link):/,
    /\/Users\//,
    /apps\/frontend/,
    /node_modules/,
    /node:/,
    /@fred\/(?:ui|design-tokens)/,
    /\b(?:React|Keycloak|ApplicationSummary)\b/,
  ]) {
    assert(
      !forbidden.test(content),
      `${relativePath} contains a forbidden framework/FRED/local reference`,
    );
  }
}

export async function assertRuntimeReferences(packageRoot, relativePath) {
  const filePath = path.join(packageRoot, relativePath);
  try {
    await run(process.execPath, ["--check", filePath]);
  } catch (error) {
    throw new Error(
      `${relativePath} has malformed module syntax: invalid native ESM syntax`,
      { cause: error },
    );
  }
  const content = await readFile(filePath, "utf8");
  const references = inspectModuleReferences(content, {
    fileName: relativePath,
    mode: "runtime",
  });
  for (const { specifier: reference } of references) {
    assert(
      reference.startsWith("."),
      `${relativePath} contains undeclared bare runtime module ${reference}`,
    );
    const resolved = confinedTarget(packageRoot, relativePath, reference);
    assert(
      await executableTarget(resolved),
      `${relativePath} has runtime reference ${reference} without an executable packed module`,
    );
  }
  assertNoForbiddenReferences(relativePath, content);
  return { content, references };
}

export async function assertDeclarationReferences(packageRoot, relativePath) {
  const content = await readFile(path.join(packageRoot, relativePath), "utf8");
  const references = inspectModuleReferences(content, {
    fileName: relativePath,
    mode: "declaration",
  });
  for (const { specifier: reference } of references) {
    assert(
      reference.startsWith("."),
      `${relativePath} contains undeclared bare declaration module ${reference}`,
    );
    const resolved = confinedTarget(packageRoot, relativePath, reference);
    assert(
      await declarationTarget(resolved),
      `${relativePath} has unresolved declaration reference ${reference} without a packed .d.ts target`,
    );
  }
  assertNoForbiddenReferences(relativePath, content);
  return { content, references };
}

async function assertExportTarget(packageRoot, exportName, condition, target) {
  assert.equal(
    typeof target,
    "string",
    `${exportName} ${condition} export must be a string`,
  );
  assert(
    target.startsWith("./"),
    `${exportName} ${condition} export must be package-relative`,
  );
  const resolved = confinedTarget(packageRoot, "package.json", target);
  if (condition === "types") {
    assert(
      await declarationTarget(resolved),
      `${exportName} types export has no packed .d.ts target`,
    );
  } else {
    assert(
      await executableTarget(resolved),
      `${exportName} runtime export has no executable packed module`,
    );
  }
}

export async function validateIframeSdkArchive(
  archivePath,
  { contract: selectedContract } = {},
) {
  const contract = selectedContract ?? (await loadReleaseContract());
  const expectedPackage = packageContract(contract, "iframeSdk");
  const temporary = await mkdtemp(
    path.join(os.tmpdir(), "fred-iframe-sdk-archive-"),
  );
  try {
    const { stdout } = await run("tar", ["-tzf", path.resolve(archivePath)]);
    assertArchiveEntriesSafe(stdout);
    await run("tar", ["-xzf", path.resolve(archivePath), "-C", temporary]);
    const packageRoot = path.join(temporary, "package");
    const files = await listArchiveFiles(packageRoot);
    assert.deepEqual(
      files,
      expectedIframeSdkArchiveFiles,
      "iframe SDK packed inventory differs from the allowlist",
    );
    await assertNoArchiveLinks(packageRoot, files);

    const manifest = JSON.parse(
      await readFile(path.join(packageRoot, "package.json"), "utf8"),
    );
    assert.equal(manifest.name, expectedPackage.name);
    assert.equal(manifest.version, expectedPackage.version);
    assert.equal(
      manifest.description,
      "Framework-independent child client for FRED application iframes",
    );
    assert.equal(manifest.license, "Apache-2.0");
    assert.equal(manifest.type, "module");
    assert.equal(manifest.sideEffects, false);
    assert.notEqual(
      manifest.private,
      true,
      "individual iframe SDK package must not be private",
    );
    assert.deepEqual(manifest.exports, expectedExports);
    assert.equal(manifest.types, "./dist/types/src/index.d.ts");
    assert.deepEqual(manifest.files, [
      "dist",
      "LICENSE",
      "README.md",
      "build-evidence.json",
    ]);
    assert.deepEqual(
      dependencyEntries(manifest),
      [],
      "iframe SDK archive must have no dependency entries",
    );
    for (const [exportName, conditions] of Object.entries(manifest.exports)) {
      for (const [condition, target] of Object.entries(conditions)) {
        await assertExportTarget(packageRoot, exportName, condition, target);
      }
    }

    for (const file of files.filter((name) => /\.(?:m?js|cjs)$/.test(name))) {
      await assertRuntimeReferences(packageRoot, file);
    }
    for (const file of files.filter((name) => name.endsWith(".d.ts"))) {
      await assertDeclarationReferences(packageRoot, file);
    }

    const licenseHash = sha256(
      await readFile(path.join(packageRoot, "LICENSE")),
    );
    assert.equal(
      licenseHash,
      approvedFredLicenseHash,
      "FRED license differs from approved complete content",
    );
    const evidence = JSON.parse(
      await readFile(path.join(packageRoot, "build-evidence.json"), "utf8"),
    );
    assert.deepEqual(evidence.sourceAllowlist, IFRAME_SDK_SOURCE_PATHS);
    assert.deepEqual(evidence.externals, []);
    assert.deepEqual(evidence.builds.index.modules, [
      "libs/frontend/iframe-sdk/.generated/applicationProtocol.ts",
      "libs/frontend/iframe-sdk/src/index.ts",
    ]);
    assert.deepEqual(evidence.builds.protocol.modules, [
      "libs/frontend/iframe-sdk/.generated/applicationProtocol.ts",
    ]);
    assert.deepEqual(evidence.builds.index.outputs, ["index.js"]);
    assert.deepEqual(evidence.builds.protocol.outputs, ["protocol.js"]);
    assert.equal(evidence.licenseSha256, licenseHash);
    const canonicalHash = sha256(
      await readFile(
        path.join(repositoryRoot, IFRAME_SDK_CANONICAL_SOURCE_PATH),
      ),
    );
    assert.deepEqual(evidence.canonicalProtocol, {
      path: IFRAME_SDK_CANONICAL_SOURCE_PATH,
      sha256: canonicalHash,
    });
    assert.deepEqual(evidence.runtimeImports, {
      "index.js": [],
      "protocol.js": [],
    });

    const combined = await Promise.all(
      files
        .filter((file) => /\.(?:json|md|m?js|cjs|d\.ts)$/.test(file))
        .map((file) => readFile(path.join(packageRoot, file), "utf8")),
    );
    assert(
      !/\bRAGS\b|rags-|rag[_-]specific/i.test(combined.join("\n")),
      "iframe SDK archive contains consumer-specific identity",
    );
    assertExpectedManifest(manifest, expectedPackage);
    return {
      package: `${manifest.name}@${manifest.version}`,
      files,
      runtimeModules: files.filter((file) => /\.(?:m?js|cjs)$/.test(file)),
      declarations: files.filter((file) => file.endsWith(".d.ts")),
      canonicalProtocolSha256: canonicalHash,
    };
  } finally {
    await rm(temporary, { recursive: true, force: true });
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const archivePath = process.argv[2];
  if (!archivePath)
    throw new Error("usage: validate-iframe-sdk-archive.mjs <archive.tgz>");
  process.stdout.write(
    `${JSON.stringify(await validateIframeSdkArchive(archivePath), null, 2)}\n`,
  );
}

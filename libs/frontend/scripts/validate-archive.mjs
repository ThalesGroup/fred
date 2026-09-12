import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";
import { lstat, mkdtemp, readFile, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import postcss from "postcss";
import valueParser from "postcss-value-parser";

import {
  assertArchiveEntriesSafe,
  assertNoArchiveLinks,
  dependencyEntries,
  listArchiveFiles,
} from "./archive-safety.mjs";
import { FONT_SOURCES, LICENSE_FILES } from "./package-inputs.mjs";
import { run } from "./process.mjs";
import {
  assertExpectedManifest,
  isLocalDependencyReference,
  loadReleaseContract,
  packageContract,
} from "./release-contract.mjs";
import {
  assertNoCssImports,
  assertTokenCssContract,
} from "./token-css-contract.mjs";

export const expectedArchiveFiles = [
  "LICENSE",
  "README.md",
  "THIRD_PARTY_NOTICES.md",
  "dist/fonts.css",
  "dist/fonts/Geist-Italic.woff2",
  "dist/fonts/Geist.woff2",
  "dist/tokens.css",
  "licenses/Geist-OFL-1.1.txt",
  "package.json",
];

const expectedExports = {
  "./tokens.css": "./dist/tokens.css",
  "./fonts.css": "./dist/fonts.css",
};

function sha256(content) {
  return createHash("sha256").update(content).digest("hex");
}

async function validateCssAssets(packageRoot, relativePath) {
  const absolutePath = path.join(packageRoot, relativePath);
  const root = postcss.parse(await readFile(absolutePath, "utf8"), {
    from: absolutePath,
  });
  if (relativePath === "dist/tokens.css") {
    assertTokenCssContract(root, relativePath);
  } else {
    assertNoCssImports(root, relativePath);
  }
  const assets = [];
  root.walkDecls((declaration) => {
    valueParser(declaration.value).walk((node) => {
      if (node.type !== "function" || node.value.toLowerCase() !== "url") {
        return;
      }
      const assetUrl = valueParser
        .stringify(node.nodes)
        .trim()
        .replace(/^(['"])(.*)\1$/, "$2");
      if (/^(?:[a-z]+:|\/)/i.test(assetUrl)) {
        throw new Error(
          `${relativePath} contains non-package asset URL: ${assetUrl}`,
        );
      }
      const resolved = path.resolve(path.dirname(absolutePath), assetUrl);
      const relativeAsset = path.relative(packageRoot, resolved);
      if (relativeAsset.startsWith("..") || path.isAbsolute(relativeAsset)) {
        throw new Error(
          `${relativePath} asset escapes the package: ${assetUrl}`,
        );
      }
      assets.push(relativeAsset.split(path.sep).join("/"));
    });
  });
  for (const asset of assets) {
    await assert.doesNotReject(
      () => lstat(path.join(packageRoot, asset)),
      `${relativePath} missing ${asset}`,
    );
  }
  return assets.sort();
}

export async function validateArchive(
  archivePath,
  { contract: selectedContract } = {},
) {
  const contract = selectedContract ?? (await loadReleaseContract());
  const expectedPackage = packageContract(contract, "designTokens");
  const archive = path.resolve(archivePath);
  const temporaryRoot = await mkdtemp(
    path.join(os.tmpdir(), "fred-package-archive-"),
  );
  try {
    const { stdout: listing } = await run("tar", ["-tzf", archive]);
    assertArchiveEntriesSafe(listing);
    await run("tar", ["-xzf", archive, "-C", temporaryRoot]);
    const packageRoot = path.join(temporaryRoot, "package");
    const files = await listArchiveFiles(packageRoot);
    assert.deepEqual(
      files,
      expectedArchiveFiles,
      "packed inventory differs from the allowlist",
    );
    await assertNoArchiveLinks(packageRoot, files);

    const manifest = JSON.parse(
      await readFile(path.join(packageRoot, "package.json"), "utf8"),
    );
    assert.equal(
      manifest.name,
      expectedPackage.name,
      "archive is not the design-token member",
    );
    assert.notEqual(
      manifest.private,
      true,
      "individual package must not inherit root privacy",
    );
    assert.deepEqual(
      manifest.files,
      ["dist", "LICENSE", "README.md", "THIRD_PARTY_NOTICES.md", "licenses"],
      "manifest files allowlist differs from the contract",
    );
    assert.deepEqual(
      manifest.sideEffects,
      ["./dist/*.css"],
      "CSS exports must remain side-effectful",
    );

    for (const [exportName, target] of Object.entries(manifest.exports)) {
      const resolved = path.resolve(packageRoot, target);
      const relativeTarget = path.relative(packageRoot, resolved);
      assert(
        !relativeTarget.startsWith("..") && !path.isAbsolute(relativeTarget),
        `export ${exportName} escapes the package: ${target}`,
      );
      await assert.doesNotReject(
        () => lstat(resolved),
        `export ${exportName} is absent: ${target}`,
      );
    }
    assert.deepEqual(
      manifest.exports,
      expectedExports,
      "public exports differ from the contract",
    );

    const dependencies = dependencyEntries(manifest);
    for (const dependency of dependencies) {
      assert(
        !isLocalDependencyReference(String(dependency.version)),
        `${dependency.field}.${dependency.name} uses a local dependency protocol`,
      );
    }
    const runtimeDependencies = dependencies.filter(({ field }) =>
      ["dependencies", "optionalDependencies", "peerDependencies"].includes(
        field,
      ),
    );
    assert.deepEqual(
      runtimeDependencies,
      [],
      "design tokens must not declare runtime dependencies",
    );

    const generatedTextFiles = [
      "dist/tokens.css",
      "dist/fonts.css",
      "package.json",
    ];
    const forbiddenReferences = [
      { pattern: /@(?:shared|rework)\b/, description: "FRED source alias" },
      {
        pattern: /(?:workspace|file|link):/,
        description: "local dependency protocol",
      },
      {
        pattern: /apps\/frontend|libs\/frontend/,
        description: "repository-relative source path",
      },
      {
        pattern: /\/[\w./-]*fred-frontend-packaging\//,
        description: "absolute checkout path",
      },
    ];
    for (const relativePath of generatedTextFiles) {
      const content = await readFile(
        path.join(packageRoot, relativePath),
        "utf8",
      );
      for (const { pattern, description } of forbiddenReferences) {
        assert(
          !pattern.test(content),
          `${relativePath} contains ${description}`,
        );
      }
    }

    const cssAssets = Object.fromEntries(
      await Promise.all(
        ["dist/tokens.css", "dist/fonts.css"].map(async (relativePath) => [
          relativePath,
          await validateCssAssets(packageRoot, relativePath),
        ]),
      ),
    );
    assert.deepEqual(
      cssAssets["dist/tokens.css"],
      [],
      "tokens.css must not request assets",
    );
    assert.deepEqual(cssAssets["dist/fonts.css"], [
      "dist/fonts/Geist-Italic.woff2",
      "dist/fonts/Geist.woff2",
    ]);

    for (const source of FONT_SOURCES) {
      const packedFont = await readFile(
        path.join(packageRoot, "dist/fonts", source.packedName),
      );
      assert.equal(
        sha256(packedFont),
        source.sha256,
        `${source.packedName} differs from provenance`,
      );
    }
    const notice = await readFile(
      path.join(packageRoot, "THIRD_PARTY_NOTICES.md"),
      "utf8",
    );
    for (const source of FONT_SOURCES) {
      assert(
        notice.includes(source.sha256),
        `notice omits ${source.packedName} hash`,
      );
    }
    const licenseHashes = {};
    for (const license of LICENSE_FILES) {
      const content = await readFile(
        path.join(packageRoot, license.packedPath),
      );
      const actualHash = sha256(content);
      assert.equal(
        actualHash,
        license.sha256,
        `${license.packedPath} differs from its approved complete content`,
      );
      licenseHashes[license.packedPath] = actualHash;
    }

    assertExpectedManifest(manifest, expectedPackage);

    return {
      archive,
      package: `${manifest.name}@${manifest.version}`,
      files,
      cssAssets,
      fontHashes: Object.fromEntries(
        FONT_SOURCES.map((source) => [source.packedName, source.sha256]),
      ),
      licenseHashes,
    };
  } finally {
    await rm(temporaryRoot, { recursive: true, force: true });
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const archivePath = process.argv[2];
  if (!archivePath) {
    throw new Error("Usage: node scripts/validate-archive.mjs <archive.tgz>");
  }
  process.stdout.write(
    `${JSON.stringify(
      await validateArchive(archivePath, {
        contract: await loadReleaseContract(
          process.argv.includes("--contract")
            ? process.argv[process.argv.indexOf("--contract") + 1]
            : undefined,
        ),
      }),
      null,
      2,
    )}\n`,
  );
}

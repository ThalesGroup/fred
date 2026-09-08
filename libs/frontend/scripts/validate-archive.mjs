import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";
import { lstat, mkdtemp, readFile, readdir, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import postcss from "postcss";
import valueParser from "postcss-value-parser";

import { FONT_SOURCES } from "./package-inputs.mjs";
import { run } from "./process.mjs";

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

async function listFiles(root, relativeDirectory = "") {
  const directory = path.join(root, relativeDirectory);
  const entries = await readdir(directory, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const relativePath = path.posix.join(relativeDirectory, entry.name);
    if (entry.isDirectory()) {
      files.push(...(await listFiles(root, relativePath)));
    } else {
      files.push(relativePath);
    }
  }
  return files.sort();
}

function dependencyEntries(manifest) {
  const fields = [
    "dependencies",
    "devDependencies",
    "optionalDependencies",
    "peerDependencies",
    "overrides",
  ];
  return fields.flatMap((field) =>
    Object.entries(manifest[field] ?? {}).map(([name, version]) => ({
      field,
      name,
      version,
    })),
  );
}

async function validateCssAssets(packageRoot, relativePath) {
  const absolutePath = path.join(packageRoot, relativePath);
  const root = postcss.parse(await readFile(absolutePath, "utf8"), {
    from: absolutePath,
  });
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

async function validateNoLinks(packageRoot, files) {
  for (const relativePath of files) {
    const stat = await lstat(path.join(packageRoot, relativePath));
    assert(
      !stat.isSymbolicLink(),
      `archive contains a symbolic link: ${relativePath}`,
    );
  }
}

export async function validateArchive(archivePath) {
  const archive = path.resolve(archivePath);
  const temporaryRoot = await mkdtemp(
    path.join(os.tmpdir(), "fred-package-archive-"),
  );
  try {
    const { stdout: listing } = await run("tar", ["-tzf", archive]);
    const archiveEntries = listing.trim().split("\n").filter(Boolean);
    for (const entry of archiveEntries) {
      assert(
        entry === "package" || entry.startsWith("package/"),
        `archive entry escapes package/: ${entry}`,
      );
      assert(
        !entry.split("/").includes(".."),
        `archive entry contains traversal: ${entry}`,
      );
    }
    await run("tar", ["-xzf", archive, "-C", temporaryRoot]);
    const packageRoot = path.join(temporaryRoot, "package");
    const files = await listFiles(packageRoot);
    assert.deepEqual(
      files,
      expectedArchiveFiles,
      "packed inventory differs from the allowlist",
    );
    await validateNoLinks(packageRoot, files);

    const manifest = JSON.parse(
      await readFile(path.join(packageRoot, "package.json"), "utf8"),
    );
    assert.equal(
      manifest.name,
      "@fred/design-tokens",
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
        !/^(?:file:|workspace:|link:)/.test(String(dependency.version)),
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
    const fontLicense = await readFile(
      path.join(packageRoot, "licenses/Geist-OFL-1.1.txt"),
      "utf8",
    );
    assert.match(fontLicense, /SIL OPEN FONT LICENSE Version 1\.1/);
    assert.match(fontLicense, /Copyright 2024 The Geist Project Authors/);
    const fredLicense = await readFile(
      path.join(packageRoot, "LICENSE"),
      "utf8",
    );
    assert.match(fredLicense, /Apache License\s+Version 2\.0/);

    return {
      archive,
      package: `${manifest.name}@${manifest.version}`,
      files,
      cssAssets,
      fontHashes: Object.fromEntries(
        FONT_SOURCES.map((source) => [source.packedName, source.sha256]),
      ),
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
    `${JSON.stringify(await validateArchive(archivePath), null, 2)}\n`,
  );
}

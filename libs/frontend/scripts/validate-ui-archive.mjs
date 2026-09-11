import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { lstat, mkdtemp, readFile, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import postcss from "postcss";
import selectorParser from "postcss-selector-parser";
import valueParser from "postcss-value-parser";
import * as fontkit from "fontkit";

import {
  assertArchiveEntriesSafe,
  assertNoArchiveLinks,
  listArchiveFiles,
} from "./archive-safety.mjs";
import { TOKEN_SOURCE_PATHS, UI_FONT_SOURCE } from "./package-inputs.mjs";
import { run } from "./process.mjs";
import {
  assertExpectedManifest,
  loadReleaseContract,
  packageContract,
} from "./release-contract.mjs";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const repositoryRoot = path.resolve(scriptDirectory, "../../..");

export const expectedUiArchiveFiles = [
  "LICENSE",
  "README.md",
  "THIRD_PARTY_NOTICES.md",
  "build-evidence.json",
  "dist/fonts/MaterialSymbolsOutlined.woff2",
  "dist/index.js",
  "dist/styles.css",
  "dist/types/.generated/src/rework/components/shared/atoms/Button/Button.d.ts",
  "dist/types/.generated/src/rework/components/shared/atoms/Icon/Icon.d.ts",
  "dist/types/.generated/src/rework/components/shared/atoms/IconButton/IconButton.d.ts",
  "dist/types/.generated/src/rework/components/shared/atoms/Spinner/Spinner.d.ts",
  "dist/types/.generated/src/rework/components/shared/atoms/TextInput/TextInput.d.ts",
  "dist/types/.generated/src/rework/components/shared/utils/Type.d.ts",
  "dist/types/src/index.d.ts",
  "licenses/Material-Symbols-Apache-2.0.txt",
  "package.json",
];

const expectedExports = {
  ".": { types: "./dist/types/src/index.d.ts", import: "./dist/index.js" },
  "./styles.css": "./dist/styles.css",
};
const approvedLicenseHash =
  "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30";
const approvedFredLicenseHash =
  "c4f0580f5e58f572f41c1985ac9920c227c166f09d25cba1a01ace86409c6e5c";
const approvedNoticeHash =
  "0fb3004cfe2a8dc6f37092003918a94af05393185807a20acfab1db7922032ce";
function isAllowedBareModule(reference) {
  return (
    reference === "react" ||
    reference.startsWith("react/") ||
    reference === "react-dom" ||
    reference.startsWith("react-dom/")
  );
}

function sha256(content) {
  return createHash("sha256").update(content).digest("hex");
}

function bareReferences(content) {
  const matches = content.matchAll(
    /(?:from\s*|import\s*\(|import\s*)["']([^"']+)["']/g,
  );
  return [...matches]
    .map((match) => match[1])
    .filter((reference) => !reference.startsWith("."));
}

async function isRegularFile(candidate) {
  return lstat(candidate).then(
    (entry) => entry.isFile(),
    () => false,
  );
}

async function assertRelativeReferences(
  packageRoot,
  relativePath,
  referenceKind,
) {
  const content = await readFile(path.join(packageRoot, relativePath), "utf8");
  for (const reference of bareReferences(content)) {
    assert(
      isAllowedBareModule(reference),
      `${relativePath} contains undeclared bare module ${reference}`,
    );
  }
  for (const match of content.matchAll(
    /(?:from\s*|import\s*\(\s*|import\s*)["'](\.[^"']+)["']/g,
  )) {
    const reference = match[1];
    const resolved = path.resolve(
      path.dirname(path.join(packageRoot, relativePath)),
      reference,
    );
    const resolvedRelative = path.relative(packageRoot, resolved);
    assert(
      !resolvedRelative.startsWith("..") && !path.isAbsolute(resolvedRelative),
      `${relativePath} has escaping reference ${reference}`,
    );
    if (referenceKind === "runtime") {
      assert(
        [".js", ".mjs", ".cjs"].includes(path.extname(resolved)) &&
          (await isRegularFile(resolved)),
        `${relativePath} has runtime reference ${reference} without an executable module`,
      );
    } else {
      const candidates = [
        resolved,
        resolved.replace(/\.(?:tsx?|jsx?|mjs|cjs)$/, ".d.ts"),
        `${resolved}.d.ts`,
        `${resolved}.js`,
      ];
      const present = await Promise.all(candidates.map(isRegularFile));
      assert(
        present.some(Boolean),
        `${relativePath} has unresolved reference ${reference} in the declaration graph`,
      );
    }
  }
  for (const forbidden of [
    /@(?:shared|rework)\b/,
    /(?:workspace|file|link):/,
    /\/Users\//,
    /apps\/frontend/,
  ]) {
    assert(
      !forbidden.test(content),
      `${relativePath} contains a forbidden FRED/local reference`,
    );
  }
  return content;
}

function selectorBranchIsContained(selector) {
  let contained = false;
  for (const node of selector.nodes) {
    if (node.type === "combinator") {
      if (["+", "~", "||"].includes(node.value.trim())) contained = false;
      continue;
    }
    if (
      node.type === "class" &&
      (node.value === "fred-ui" || /^_[A-Za-z0-9_-]+$/.test(node.value))
    ) {
      contained = true;
      continue;
    }
    if (
      node.type === "pseudo" &&
      [":is", ":where"].includes(node.value.toLowerCase()) &&
      node.nodes?.length > 0 &&
      node.nodes.every(selectorBranchIsContained)
    ) {
      contained = true;
    }
  }
  return contained;
}

function assertSelectorContained(selector) {
  let parsed;
  try {
    parsed = selectorParser().astSync(selector);
  } catch {
    assert.fail(`UI CSS selector ${selector} cannot be structurally parsed`);
  }
  assert(
    parsed.nodes.length > 0 && parsed.nodes.every(selectorBranchIsContained),
    `UI CSS contains unscoped non-module selector ${selector}: not contained in the permitted UI scope`,
  );
}

async function validateCss(packageRoot) {
  const relativePath = "dist/styles.css";
  const absolutePath = path.join(packageRoot, relativePath);
  const css = await readFile(absolutePath, "utf8");
  const root = postcss.parse(css, { from: absolutePath });
  root.walkAtRules((rule) =>
    assert.notEqual(
      rule.name.toLowerCase(),
      "import",
      "UI CSS must not contain @import",
    ),
  );
  assert(
    css.includes(".fred-ui"),
    "UI CSS is missing the consumer-owned .fred-ui root",
  );
  root.walkRules((rule) => {
    if (rule.parent?.type === "atrule" && /keyframes$/i.test(rule.parent.name))
      return;
    for (const selector of rule.selectors ?? []) {
      assert(
        !/(^|[\s,>+~])(?:html|body|:root)(?=$|[\s,>+~.:#[])/i.test(selector),
        `UI CSS contains shell selector ${selector}`,
      );
      assertSelectorContained(selector);
    }
  });
  for (const property of ["overflow", "user-select"]) {
    root.walkDecls(new RegExp(`^${property}$`, "i"), (declaration) => {
      const selectors = declaration.parent?.selectors ?? [];
      assert(
        selectors.every(
          (selector) =>
            !selector.includes(".fred-ui") || selector.includes("_"),
        ),
        `UI base CSS contains shell behavior ${property}`,
      );
    });
  }
  const assets = [];
  root.walkDecls((declaration) => {
    valueParser(declaration.value).walk((node) => {
      if (node.type !== "function" || node.value.toLowerCase() !== "url")
        return;
      const url = valueParser
        .stringify(node.nodes)
        .trim()
        .replace(/^(['"])(.*)\1$/, "$2");
      assert(
        !/^(?:[a-z]+:|\/)/i.test(url),
        `UI CSS contains non-package URL ${url}`,
      );
      assets.push(path.posix.normalize(path.posix.join("dist", url)));
    });
  });
  assert.deepEqual(assets, ["dist/fonts/MaterialSymbolsOutlined.woff2"]);

  const tokenRoots = await Promise.all(
    TOKEN_SOURCE_PATHS.map(async (sourcePath) => {
      const absolutePath = path.join(repositoryRoot, sourcePath);
      return postcss.parse(await readFile(absolutePath, "utf8"), {
        from: absolutePath,
      });
    }),
  );
  const definitions = new Set();
  const references = new Set();
  for (const stylesheet of [...tokenRoots, root]) {
    stylesheet.walkDecls((declaration) => {
      if (declaration.prop.startsWith("--")) definitions.add(declaration.prop);
      valueParser(declaration.value).walk((node) => {
        if (node.type !== "function" || node.value.toLowerCase() !== "var")
          return;
        const reference = valueParser
          .stringify(node.nodes)
          .split(",", 1)[0]
          .trim();
        if (reference.startsWith("--")) references.add(reference);
      });
    });
  }
  assert.deepEqual(
    [...references].filter((reference) => !definitions.has(reference)).sort(),
    [],
    "UI CSS contains custom-property references absent from the design-token and UI stylesheets",
  );
  return { css, assets };
}

export async function validateUiArchive(
  archivePath,
  { contract: selectedContract } = {},
) {
  const contract = selectedContract ?? (await loadReleaseContract());
  const expectedPackage = packageContract(contract, "ui");
  const temporary = await mkdtemp(path.join(os.tmpdir(), "fred-ui-archive-"));
  try {
    const { stdout } = await run("tar", ["-tzf", path.resolve(archivePath)]);
    assertArchiveEntriesSafe(stdout);
    await run("tar", ["-xzf", path.resolve(archivePath), "-C", temporary]);
    const packageRoot = path.join(temporary, "package");
    const files = await listArchiveFiles(packageRoot);
    assert.deepEqual(
      files,
      expectedUiArchiveFiles,
      "UI packed inventory differs from the allowlist",
    );
    await assertNoArchiveLinks(packageRoot, files);

    const manifest = JSON.parse(
      await readFile(path.join(packageRoot, "package.json"), "utf8"),
    );
    assert.equal(manifest.name, expectedPackage.name);
    assert.notEqual(
      manifest.private,
      true,
      "individual UI package must not be private",
    );
    for (const [exportName, contract] of Object.entries(
      manifest.exports ?? {},
    )) {
      for (const target of typeof contract === "string"
        ? [contract]
        : Object.values(contract)) {
        const resolved = path.resolve(packageRoot, target);
        const relative = path.relative(packageRoot, resolved);
        assert(
          !relative.startsWith("..") && !path.isAbsolute(relative),
          `export ${exportName} escapes the package: ${target}`,
        );
        await assert.doesNotReject(
          () => lstat(resolved),
          `export ${exportName} is absent: ${target}`,
        );
      }
    }
    assert.deepEqual(manifest.exports, expectedExports);
    assert.deepEqual(
      manifest.dependencies ?? {},
      {},
      "UI package must use peers, not runtime dependencies",
    );
    for (const fields of [
      manifest.dependencies,
      manifest.peerDependencies,
      manifest.optionalDependencies,
    ]) {
      for (const version of Object.values(fields ?? {}))
        assert(
          !/^(?:file:|workspace:|link:)/.test(String(version)),
          "local dependency protocol",
        );
    }
    assert.deepEqual(
      manifest.peerDependencies,
      expectedPackage.expectedManifest.peerDependencies,
    );

    const js = await assertRelativeReferences(
      packageRoot,
      "dist/index.js",
      "runtime",
    );
    for (const forbidden of [
      "customAgent",
      "material-symbols-rounded",
      "material-symbols-sharp",
      "/images/icons/",
    ])
      assert(
        !js.includes(forbidden),
        `UI JavaScript contains application-only icon behavior ${forbidden}`,
      );
    const declarations = files.filter((file) => file.endsWith(".d.ts"));
    for (const file of declarations) {
      const declaration = await assertRelativeReferences(
        packageRoot,
        file,
        "declaration",
      );
      assert(
        !/\b(?:IconCategory|IconType|CustomIconType|isCustomIcon|toIconType)\b|customAgent|material-symbols-(?:rounded|sharp)|\/images\/icons\//.test(
          declaration,
        ),
        `${file} contains application-only icon declarations`,
      );
    }
    const { assets } = await validateCss(packageRoot);
    const fontHash = sha256(await readFile(path.join(packageRoot, assets[0])));
    assert.equal(
      fontHash,
      UI_FONT_SOURCE.sha256,
      "packed Material Symbols binary differs from provenance",
    );
    const licenseHash = sha256(
      await readFile(
        path.join(packageRoot, "licenses/Material-Symbols-Apache-2.0.txt"),
      ),
    );
    assert.equal(
      licenseHash,
      approvedLicenseHash,
      "Material Symbols license differs from approved complete content",
    );
    const fredLicenseHash = sha256(
      await readFile(path.join(packageRoot, "LICENSE")),
    );
    assert.equal(
      fredLicenseHash,
      approvedFredLicenseHash,
      "FRED license differs from approved complete content",
    );
    const noticeContent = await readFile(
      path.join(packageRoot, "THIRD_PARTY_NOTICES.md"),
    );
    assert.equal(
      sha256(noticeContent),
      approvedNoticeHash,
      "third-party notice differs from approved complete content",
    );
    const notice = noticeContent.toString("utf8");
    assert(
      notice.includes(UI_FONT_SOURCE.sha256),
      "third-party notice omits font hash",
    );

    const typeDeclarations = await readFile(
      path.join(
        packageRoot,
        "dist/types/.generated/src/rework/components/shared/utils/Type.d.ts",
      ),
      "utf8",
    );
    const inventoryMatch = typeDeclarations.match(
      /materialIcons:\s*readonly\s*\[([^;]+)\];/,
    );
    assert(
      inventoryMatch,
      "MaterialIconType declaration has no closed glyph inventory",
    );
    const glyphs = [...inventoryMatch[1].matchAll(/"([^"]+)"/g)].map(
      (match) => match[1],
    );
    const font = fontkit.openSync(path.join(packageRoot, assets[0]));
    const unsupportedGlyphs = glyphs.filter((name) => {
      const run = font.layout(name, ["liga"]);
      return run.glyphs.length !== 1 || run.glyphs[0].id === 0;
    });
    assert.deepEqual(
      unsupportedGlyphs,
      [],
      `unsupported packed Material Symbols names: ${unsupportedGlyphs.join(", ")}`,
    );

    const evidence = JSON.parse(
      await readFile(path.join(packageRoot, "build-evidence.json"), "utf8"),
    );
    assert.deepEqual(evidence.externals, [
      "react",
      "react/*",
      "react-dom",
      "react-dom/*",
    ]);
    for (const runtime of ["react", "react/jsx-runtime"]) {
      assert(
        evidence.modules.some(
          (module) => module.id === runtime && module.external,
        ),
        `${runtime} is not proven external`,
      );
    }
    assert(
      !evidence.modules.some(
        (module) =>
          /node_modules\/(?:react|react-dom)\//.test(module.id) &&
          !module.external,
      ),
      "React runtime was bundled",
    );
    assert.equal(evidence.glyphs.sha256, UI_FONT_SOURCE.sha256);
    assert.deepEqual(
      evidence.glyphs.glyphs,
      glyphs,
      "build evidence and declared glyph inventory differ",
    );
    assert.match(js, /from\s+"react\/jsx-runtime"/);
    assertExpectedManifest(manifest, expectedPackage);
    return {
      archive: path.resolve(archivePath),
      package: `${manifest.name}@${manifest.version}`,
      files,
      assets,
      fontHash,
      fredLicenseHash,
      licenseHash,
      glyphCount: glyphs.length,
      externalModules: evidence.modules
        .filter(({ external }) => external)
        .map(({ id }) => id),
    };
  } finally {
    await rm(temporary, { recursive: true, force: true });
  }
}

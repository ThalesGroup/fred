import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdtemp, mkdir, readFile, rm, writeFile, cp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import postcss from "postcss";
import valueParser from "postcss-value-parser";

import {
  buildDesignTokens,
  defaultPackageRoot,
  defaultRepositoryRoot,
} from "../scripts/build-design-tokens.mjs";
import {
  FONT_SOURCES,
  FONT_STYLESHEET_PATH,
  ROOT_LICENSE_PATH,
  TOKEN_SOURCE_PATHS,
} from "../scripts/package-inputs.mjs";

function hash(content) {
  return createHash("sha256").update(content).digest("hex");
}

async function createFixture() {
  const fixtureRoot = await mkdtemp(
    path.join(os.tmpdir(), "fred-token-generator-"),
  );
  const repositoryRoot = path.join(fixtureRoot, "repository");
  const packageRoot = path.join(fixtureRoot, "package");
  const copiedPaths = [
    ...TOKEN_SOURCE_PATHS,
    FONT_STYLESHEET_PATH,
    ...FONT_SOURCES.map(({ sourcePath }) => sourcePath),
    ROOT_LICENSE_PATH,
  ];
  for (const relativePath of copiedPaths) {
    const destination = path.join(repositoryRoot, relativePath);
    await mkdir(path.dirname(destination), { recursive: true });
    await cp(path.join(defaultRepositoryRoot, relativePath), destination);
  }
  await mkdir(path.join(packageRoot, "license-inputs"), { recursive: true });
  await cp(
    path.join(defaultPackageRoot, "license-inputs/Geist-OFL-1.1.txt"),
    path.join(packageRoot, "license-inputs/Geist-OFL-1.1.txt"),
  );
  return { fixtureRoot, repositoryRoot, packageRoot };
}

test("generates the token AST in canonical source order", async () => {
  await buildDesignTokens();
  const generated = postcss.parse(
    await readFile(path.join(defaultPackageRoot, "dist/tokens.css"), "utf8"),
  );
  const expectedNodes = [];
  for (const sourcePath of TOKEN_SOURCE_PATHS) {
    const source = postcss.parse(
      await readFile(path.join(defaultRepositoryRoot, sourcePath), "utf8"),
    );
    expectedNodes.push(...source.nodes.map((node) => node.toString()));
  }
  assert.deepEqual(
    generated.nodes.map((node) => node.toString()),
    expectedNodes,
  );
});

test("keeps themes neutral and fonts explicitly separate", async () => {
  await buildDesignTokens();
  const tokens = postcss.parse(
    await readFile(path.join(defaultPackageRoot, "dist/tokens.css"), "utf8"),
  );
  const selectors = [];
  let fontFaceCount = 0;
  tokens.walkRules((rule) => selectors.push(...(rule.selectors ?? [])));
  tokens.walkAtRules("font-face", () => fontFaceCount++);
  assert.equal(fontFaceCount, 0);
  assert(selectors.includes('[data-theme="light"]'));
  assert(selectors.includes('[data-theme="dark"]'));
  assert(
    !selectors.some((selector) =>
      ["*", "html", "body"].includes(selector.trim()),
    ),
  );
  assert(!tokens.toString().includes("Material Symbols"));

  const fonts = postcss.parse(
    await readFile(path.join(defaultPackageRoot, "dist/fonts.css"), "utf8"),
  );
  const faces = [];
  fonts.walkAtRules("font-face", (rule) => {
    const declarations = Object.fromEntries(
      rule.nodes
        .filter((node) => node.type === "decl")
        .map((node) => [node.prop, node.value]),
    );
    faces.push(declarations);
  });
  assert.deepEqual(
    faces.map(({ "font-style": style }) => style),
    ["normal", "italic"],
  );
  for (const [index, face] of faces.entries()) {
    assert.equal(face["font-family"], '"Geist"');
    const urls = [];
    valueParser(face.src).walk((node) => {
      if (node.type === "function" && node.value === "url") {
        urls.push(valueParser.stringify(node.nodes).replaceAll('"', ""));
      }
    });
    assert.deepEqual(urls, [`./fonts/${FONT_SOURCES[index].packedName}`]);
  }
});

test("rebuilds deterministically from clean generated output", async () => {
  const first = await buildDesignTokens();
  const firstHashes = await Promise.all(
    first.outputs.map(async (relativePath) =>
      hash(await readFile(path.join(defaultPackageRoot, relativePath))),
    ),
  );
  await rm(path.join(defaultPackageRoot, "dist"), { recursive: true });
  const second = await buildDesignTokens();
  const secondHashes = await Promise.all(
    second.outputs.map(async (relativePath) =>
      hash(await readFile(path.join(defaultPackageRoot, relativePath))),
    ),
  );
  assert.deepEqual(secondHashes, firstHashes);
});

test("reflects a canonical token edit without a package-side source copy", async (context) => {
  const fixture = await createFixture();
  context.after(() =>
    rm(fixture.fixtureRoot, { recursive: true, force: true }),
  );
  const spacingPath = path.join(
    fixture.repositoryRoot,
    "apps/frontend/src/styles/spacings.css",
  );
  const original = await readFile(spacingPath, "utf8");
  await writeFile(
    spacingPath,
    original.replace("--spacing-m: 16px", "--spacing-m: 17px"),
  );
  await buildDesignTokens(fixture);
  const generated = await readFile(
    path.join(fixture.packageRoot, "dist/tokens.css"),
    "utf8",
  );
  assert.match(generated, /--spacing-m: 17px/);
  assert(!generated.includes("--spacing-m: 16px"));
});

for (const importName of ["import", "ImPoRt", "IMPORT"]) {
  test(`rejects canonical @${importName}`, async (context) => {
    const fixture = await createFixture();
    context.after(() =>
      rm(fixture.fixtureRoot, { recursive: true, force: true }),
    );
    const sourcePath = path.join(
      fixture.repositoryRoot,
      "apps/frontend/src/styles/spacings.css",
    );
    await writeFile(
      sourcePath,
      `${await readFile(sourcePath, "utf8")}\n@${importName} "./missing.css";\n`,
    );
    await assert.rejects(
      () => buildDesignTokens(fixture),
      /must not contain @import/,
    );
  });
}

for (const shellRule of [
  {
    name: "ordinary shell declarations",
    css: ":root { overflow: hidden; user-select: none; }",
    error: /may declare only custom properties/,
  },
  {
    name: "an unreviewed compound selector",
    css: "html body { overflow: hidden; }",
    error: /selector is not permitted: html body/,
  },
]) {
  test(`rejects ${shellRule.name} in canonical tokens`, async (context) => {
    const fixture = await createFixture();
    context.after(() =>
      rm(fixture.fixtureRoot, { recursive: true, force: true }),
    );
    const sourcePath = path.join(
      fixture.repositoryRoot,
      "apps/frontend/src/styles/spacings.css",
    );
    await writeFile(
      sourcePath,
      `${await readFile(sourcePath, "utf8")}\n${shellRule.css}\n`,
    );
    await assert.rejects(() => buildDesignTokens(fixture), shellRule.error);
  });
}

test("rejects a missing canonical Geist asset", async (context) => {
  const fixture = await createFixture();
  context.after(() =>
    rm(fixture.fixtureRoot, { recursive: true, force: true }),
  );
  await rm(path.join(fixture.repositoryRoot, FONT_SOURCES[0].sourcePath));
  await assert.rejects(() => buildDesignTokens(fixture), /Geist\.woff2|ENOENT/);
});

test("rejects ambiguous canonical Geist declarations", async (context) => {
  const fixture = await createFixture();
  context.after(() =>
    rm(fixture.fixtureRoot, { recursive: true, force: true }),
  );
  const stylesheetPath = path.join(
    fixture.repositoryRoot,
    FONT_STYLESHEET_PATH,
  );
  const stylesheet = await readFile(stylesheetPath, "utf8");
  const normalFace = stylesheet.match(
    /@font-face\s*\{[^}]*Geist\.woff2[^}]*\}/s,
  )?.[0];
  assert(normalFace);
  await writeFile(stylesheetPath, `${stylesheet}\n${normalFace}\n`);
  await assert.rejects(
    () => buildDesignTokens(fixture),
    /Expected 2 Geist faces, found 3/,
  );
});

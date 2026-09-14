import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";
import { copyFile, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";

import postcss from "postcss";
import valueParser from "postcss-value-parser";

import {
  FONT_SOURCES,
  FONT_STYLESHEET_PATH,
  ROOT_LICENSE_PATH,
  TOKEN_SOURCE_PATHS,
} from "./package-inputs.mjs";
import {
  assertNoCssImports,
  assertTokenCssContract,
} from "./token-css-contract.mjs";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
export const defaultRepositoryRoot = path.resolve(scriptDirectory, "../../..");
export const defaultPackageRoot = path.resolve(
  scriptDirectory,
  "../design-tokens",
);

function normalizeCssString(value) {
  return value.trim().replace(/^(['"])(.*)\1$/, "$2");
}

function sha256(content) {
  return createHash("sha256").update(content).digest("hex");
}

function readSingleUrl(value, sourceDescription) {
  const parsed = valueParser(value);
  const urls = [];
  parsed.walk((node) => {
    if (node.type === "function" && node.value.toLowerCase() === "url") {
      urls.push(
        valueParser
          .stringify(node.nodes)
          .trim()
          .replace(/^(['"])(.*)\1$/, "$2"),
      );
    }
  });
  if (urls.length !== 1) {
    throw new Error(
      `${sourceDescription} must contain exactly one local url(), found ${urls.length}`,
    );
  }
  return { parsed, url: urls[0] };
}

function rewriteSingleUrl(value, packedName, sourceDescription) {
  const { parsed } = readSingleUrl(value, sourceDescription);
  parsed.walk((node) => {
    if (node.type === "function" && node.value.toLowerCase() === "url") {
      node.nodes = [
        { type: "string", quote: '"', value: `./fonts/${packedName}` },
      ];
    }
  });
  return parsed.toString();
}

async function buildTokens(repositoryRoot) {
  const output = postcss.root();
  for (const sourcePath of TOKEN_SOURCE_PATHS) {
    const absolutePath = path.join(repositoryRoot, sourcePath);
    const css = await readFile(absolutePath, "utf8");
    const parsed = postcss.parse(css, { from: absolutePath });
    assertNoCssImports(parsed, sourcePath);
    output.append(parsed.nodes.map((node) => node.clone()));
  }
  assertTokenCssContract(output, "generated tokens.css");
  return `${output.toString().trim()}\n`;
}

async function buildFonts(repositoryRoot) {
  const stylesheetPath = path.join(repositoryRoot, FONT_STYLESHEET_PATH);
  const stylesheet = postcss.parse(await readFile(stylesheetPath, "utf8"), {
    from: stylesheetPath,
  });
  const output = postcss.root();
  const matches = [];

  stylesheet.walkAtRules("font-face", (rule) => {
    const declarations = new Map();
    rule.walkDecls((declaration) =>
      declarations.set(declaration.prop, declaration),
    );
    if (
      normalizeCssString(declarations.get("font-family")?.value ?? "") !==
      "Geist"
    ) {
      return;
    }
    const style = declarations.get("font-style")?.value;
    const source = FONT_SOURCES.find((candidate) => candidate.style === style);
    if (!source) {
      throw new Error(
        `Unexpected Geist font style in ${FONT_STYLESHEET_PATH}: ${style ?? "missing"}`,
      );
    }
    const sourceDeclaration = declarations.get("src");
    if (!sourceDeclaration) {
      throw new Error(`Geist ${style} face has no src declaration`);
    }
    const { url } = readSingleUrl(
      sourceDeclaration.value,
      `Geist ${style} face`,
    );
    const resolvedSource = path.resolve(path.dirname(stylesheetPath), url);
    const expectedSource = path.join(repositoryRoot, source.sourcePath);
    if (resolvedSource !== expectedSource) {
      throw new Error(
        `Geist ${style} face resolves to ${resolvedSource}, expected ${expectedSource}`,
      );
    }
    const clonedRule = rule.clone();
    clonedRule.walkDecls("src", (declaration) => {
      declaration.value = rewriteSingleUrl(
        declaration.value,
        source.packedName,
        `Geist ${style} face`,
      );
    });
    matches.push({ rule: clonedRule, source });
  });

  if (matches.length !== FONT_SOURCES.length) {
    throw new Error(
      `Expected ${FONT_SOURCES.length} Geist faces, found ${matches.length}`,
    );
  }
  for (const expected of FONT_SOURCES) {
    if (
      matches.filter(({ source }) => source.style === expected.style).length !==
      1
    ) {
      throw new Error(`Expected exactly one Geist ${expected.style} face`);
    }
  }
  output.append(matches.map(({ rule }) => rule));
  return {
    css: `${output.toString().trim()}\n`,
    sources: matches.map(({ source }) => source),
  };
}

export async function buildDesignTokens({
  repositoryRoot = defaultRepositoryRoot,
  packageRoot = defaultPackageRoot,
} = {}) {
  const distributionRoot = path.join(packageRoot, "dist");
  const fontOutputRoot = path.join(distributionRoot, "fonts");
  const licenseOutputRoot = path.join(packageRoot, "licenses");
  await Promise.all([
    rm(distributionRoot, { recursive: true, force: true }),
    rm(path.join(packageRoot, "LICENSE"), { force: true }),
    rm(licenseOutputRoot, { recursive: true, force: true }),
  ]);
  await Promise.all([
    mkdir(fontOutputRoot, { recursive: true }),
    mkdir(licenseOutputRoot, { recursive: true }),
  ]);

  const [tokensCss, fonts] = await Promise.all([
    buildTokens(repositoryRoot),
    buildFonts(repositoryRoot),
  ]);
  for (const source of fonts.sources) {
    const content = await readFile(
      path.join(repositoryRoot, source.sourcePath),
    );
    const actualHash = sha256(content);
    if (actualHash !== source.sha256) {
      throw new Error(
        `Provenance hash mismatch for ${source.sourcePath}: expected ${source.sha256}, got ${actualHash}`,
      );
    }
    await writeFile(path.join(fontOutputRoot, source.packedName), content);
  }

  await Promise.all([
    writeFile(path.join(distributionRoot, "tokens.css"), tokensCss),
    writeFile(path.join(distributionRoot, "fonts.css"), fonts.css),
    copyFile(
      path.join(repositoryRoot, ROOT_LICENSE_PATH),
      path.join(packageRoot, "LICENSE"),
    ),
    copyFile(
      path.join(packageRoot, "license-inputs/Geist-OFL-1.1.txt"),
      path.join(licenseOutputRoot, "Geist-OFL-1.1.txt"),
    ),
  ]);

  return {
    distributionRoot,
    outputs: [
      "dist/tokens.css",
      "dist/fonts.css",
      ...FONT_SOURCES.map(({ packedName }) => `dist/fonts/${packedName}`),
      "LICENSE",
      "licenses/Geist-OFL-1.1.txt",
    ],
  };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const result = await buildDesignTokens();
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
}

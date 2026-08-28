// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { lstat, mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import { dirname, relative, resolve, sep } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import * as csstree from "css-tree";
import ts from "typescript";

const MANIFEST_FILENAME = "fred-app.json";
const FRONTEND_DIRECTORY_NAME = "frontend";
const MODULE_FILENAME = "index.tsx";
const DEFAULT_ICON = "extension";
const HOST_LOCALES = ["en", "fr"];
const APPLICATION_STYLESHEET_AT_RULES = new Set(["media", "supports", "container", "keyframes", "-webkit-keyframes"]);
const RESERVED_IDS = new Set(["constructor", "prototype"]);
const ID_PATTERN = /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/;
const SEMVER_PATTERN =
  /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-((?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*))?(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$/;
const MANIFEST_KEYS = new Set([
  "schema_version",
  "id",
  "version",
  "display_name",
  "description",
  "icon",
  "host_api_version",
  "module_key",
  "service_required",
]);
const REQUIRED_MANIFEST_KEYS = [...MANIFEST_KEYS].filter((key) => key !== "icon");

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const frontendRoot = resolve(scriptDirectory, "..");
const repositoryRoot = resolve(frontendRoot, "../..");

function readSupportedIcons() {
  const sourcePath = resolve(frontendRoot, "src/rework/components/shared/utils/Type.ts");
  const source = readFileSync(sourcePath, "utf8");
  const array = source.match(/export const materialIcons = \[([\s\S]*?)\] as const;/);
  assert(array, `${sourcePath}: could not find the materialIcons allowlist`);
  const icons = [...array[1].matchAll(/^\s*"([a-z0-9_]+)",?\s*$/gm)].map((match) => match[1]);
  assert(icons.length > 0, `${sourcePath}: materialIcons allowlist is empty`);
  return new Set(icons);
}

const SUPPORTED_ICONS = readSupportedIcons();
assert(SUPPORTED_ICONS.has(DEFAULT_ICON), `default application icon ${DEFAULT_ICON} is not supported by Fred`);

export const DEFAULT_PATHS = Object.freeze({
  applicationsDirectory: resolve(repositoryRoot, "apps/applications"),
  frontendOutput: resolve(frontendRoot, "src/rework/features/applications/generated/applicationRegistry.ts"),
  runtimeOutput: resolve(frontendRoot, "generated/application-runtime.json"),
  controlPlaneOutput: resolve(
    repositoryRoot,
    "apps/control-plane-backend/control_plane_backend/applications/catalog.generated.json",
  ),
});

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function compareStrings(left, right) {
  return left < right ? -1 : left > right ? 1 : 0;
}

function renderJavaScriptKey(key) {
  return /^[A-Za-z_$][A-Za-z0-9_$]*$/.test(key) ? key : JSON.stringify(key);
}

function isCanonicalLocale(locale) {
  try {
    const canonical = Intl.getCanonicalLocales(locale);
    return canonical.length === 1 && canonical[0] === locale;
  } catch {
    return false;
  }
}

function assertExactKeys(value, allowedKeys, requiredKeys, source) {
  for (const key of Object.keys(value)) {
    assert(allowedKeys.has(key), `${source}: unsupported field ${JSON.stringify(key)}`);
  }
  for (const key of requiredKeys) {
    assert(Object.hasOwn(value, key), `${source}: missing required field ${JSON.stringify(key)}`);
  }
}

function normalizeLocalizedText(value, field, source) {
  assert(isObject(value), `${source}: ${field} must be an object`);
  assert(Object.hasOwn(value, "en"), `${source}: ${field} must provide an English fallback`);

  const normalized = {};
  for (const locale of Object.keys(value).sort()) {
    const text = value[locale];
    assert(isCanonicalLocale(locale), `${source}: ${field} has invalid locale ${JSON.stringify(locale)}`);
    assert(
      typeof text === "string" && text.trim().length > 0,
      `${source}: ${field}.${locale} must be a non-empty string`,
    );
    assert(!/<\/?[A-Za-z][^>]*>/.test(text), `${source}: ${field}.${locale} must not contain raw HTML`);
    normalized[locale] = text.trim();
  }
  return normalized;
}

export function validateManifest(manifest, { directoryName, source = MANIFEST_FILENAME } = {}) {
  assert(isObject(manifest), `${source}: manifest must be a JSON object`);
  assertExactKeys(manifest, MANIFEST_KEYS, REQUIRED_MANIFEST_KEYS, source);
  assert(manifest.schema_version === "1", `${source}: schema_version must be "1"`);
  assert(
    typeof manifest.id === "string" && manifest.id.length <= 251 && ID_PATTERN.test(manifest.id),
    `${source}: id must be a lowercase slug no longer than 251 characters`,
  );
  assert(!RESERVED_IDS.has(manifest.id), `${source}: id ${JSON.stringify(manifest.id)} is reserved`);
  assert(
    directoryName === undefined || manifest.id === directoryName,
    `${source}: manifest id ${JSON.stringify(manifest.id)} must match directory ${JSON.stringify(directoryName)}`,
  );
  assert(
    typeof manifest.version === "string" && SEMVER_PATTERN.test(manifest.version),
    `${source}: version must be a semantic version`,
  );
  assert(manifest.host_api_version === "1", `${source}: unsupported host_api_version`);
  assert(
    typeof manifest.module_key === "string" && manifest.module_key === manifest.id,
    `${source}: module_key must match manifest id`,
  );
  assert(typeof manifest.service_required === "boolean", `${source}: service_required must be a boolean`);

  const icon = manifest.icon ?? DEFAULT_ICON;
  assert(
    typeof icon === "string" && SUPPORTED_ICONS.has(icon),
    `${source}: icon must be one of ${[...SUPPORTED_ICONS].sort().join(", ")}`,
  );

  return {
    schema_version: "1",
    id: manifest.id,
    version: manifest.version,
    display_name: normalizeLocalizedText(manifest.display_name, "display_name", source),
    description: normalizeLocalizedText(manifest.description, "description", source),
    icon,
    host_api_version: "1",
    module_key: manifest.module_key,
    service_required: manifest.service_required,
  };
}

function canonicalize(value) {
  if (Array.isArray(value)) {
    return value.map(canonicalize);
  }
  if (!isObject(value)) {
    return value;
  }
  return Object.fromEntries(
    Object.keys(value)
      .sort()
      .map((key) => [key, canonicalize(value[key])]),
  );
}

function digest(value) {
  return `sha256:${createHash("sha256")
    .update(JSON.stringify(canonicalize(value)))
    .digest("hex")}`;
}

export async function discoverApplications(applicationsDirectory = DEFAULT_PATHS.applicationsDirectory) {
  if (!existsSync(applicationsDirectory)) {
    return [];
  }

  const entries = await readdir(applicationsDirectory, { withFileTypes: true });
  const applications = [];
  for (const entry of entries.filter((item) => item.isDirectory()).sort((a, b) => compareStrings(a.name, b.name))) {
    const applicationDirectory = resolve(applicationsDirectory, entry.name);
    const frontendDirectory = resolve(applicationDirectory, FRONTEND_DIRECTORY_NAME);
    const manifestPath = resolve(applicationDirectory, MANIFEST_FILENAME);
    const modulePath = resolve(frontendDirectory, MODULE_FILENAME);
    assert(existsSync(manifestPath), `${entry.name}: missing ${MANIFEST_FILENAME}`);
    assert(existsSync(modulePath), `${entry.name}: missing ${FRONTEND_DIRECTORY_NAME}/${MODULE_FILENAME}`);

    const [manifestStats, frontendStats, moduleStats] = await Promise.all([
      lstat(manifestPath),
      lstat(frontendDirectory),
      lstat(modulePath),
    ]);
    assert(
      manifestStats.isFile() && !manifestStats.isSymbolicLink(),
      `${entry.name}: ${MANIFEST_FILENAME} must be a regular file`,
    );
    assert(
      frontendStats.isDirectory() && !frontendStats.isSymbolicLink(),
      `${entry.name}: ${FRONTEND_DIRECTORY_NAME} must be a regular directory`,
    );
    assert(
      moduleStats.isFile() && !moduleStats.isSymbolicLink(),
      `${entry.name}: ${FRONTEND_DIRECTORY_NAME}/${MODULE_FILENAME} must be a regular file`,
    );

    let parsed;
    try {
      parsed = JSON.parse(await readFile(manifestPath, "utf8"));
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      throw new Error(`${manifestPath}: invalid JSON: ${detail}`);
    }
    const manifest = validateManifest(parsed, { directoryName: entry.name, source: manifestPath });
    await validateApplicationImports(frontendDirectory);
    applications.push({ directoryName: entry.name, manifest });
  }
  return applications;
}

function buildLocaleResources(applications) {
  const locales = new Set(HOST_LOCALES);
  for (const { manifest } of applications) {
    Object.keys(manifest.display_name).forEach((locale) => locales.add(locale));
    Object.keys(manifest.description).forEach((locale) => locales.add(locale));
  }

  const resources = {};
  for (const locale of [...locales].sort()) {
    const applicationsById = {};
    for (const { manifest } of applications) {
      applicationsById[manifest.id] = {
        name: manifest.display_name[locale] ?? manifest.display_name.en,
        description: manifest.description[locale] ?? manifest.description.en,
      };
    }
    resources[locale] = { applications: applicationsById };
  }
  return resources;
}

function relativeImportPath(frontendOutput, applicationsDirectory, applicationId) {
  const modulePath = resolve(applicationsDirectory, applicationId, FRONTEND_DIRECTORY_NAME, MODULE_FILENAME);
  const path = relative(dirname(frontendOutput), modulePath).split(sep).join("/");
  return path.startsWith(".") ? path : `./${path}`;
}

function isInsideDirectory(parentDirectory, candidatePath) {
  const relativePath = relative(parentDirectory, candidatePath);
  return relativePath === "" || (!relativePath.startsWith(`..${sep}`) && relativePath !== "..");
}

function validateModuleSpecifier(specifier, sourcePath, applicationDirectory) {
  if (["react", "react/jsx-runtime", "react/jsx-dev-runtime", "@fred/application-host"].includes(specifier)) {
    return;
  }
  if (specifier.startsWith("./") || specifier.startsWith("../")) {
    if (/\.(?:css|scss|sass|less|styl)$/i.test(specifier)) {
      assert(/\.module\.css$/i.test(specifier), `${sourcePath}: application styles must use a local .module.css file`);
    }
    const target = resolve(dirname(sourcePath), specifier);
    assert(
      isInsideDirectory(applicationDirectory, target),
      `${sourcePath}: import ${JSON.stringify(specifier)} escapes its application directory`,
    );
    return;
  }
  throw new Error(
    `${sourcePath}: import ${JSON.stringify(specifier)} is outside the React and @fred/application-host boundary`,
  );
}

function validateTypeScriptImports(source, sourcePath, applicationDirectory) {
  const sourceFile = ts.createSourceFile(sourcePath, source, ts.ScriptTarget.Latest, true);

  function validateNode(node) {
    if (
      (ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) &&
      node.moduleSpecifier &&
      ts.isStringLiteralLike(node.moduleSpecifier)
    ) {
      validateModuleSpecifier(node.moduleSpecifier.text, sourcePath, applicationDirectory);
    } else if (
      ts.isImportEqualsDeclaration(node) &&
      ts.isExternalModuleReference(node.moduleReference) &&
      node.moduleReference.expression &&
      ts.isStringLiteralLike(node.moduleReference.expression)
    ) {
      validateModuleSpecifier(node.moduleReference.expression.text, sourcePath, applicationDirectory);
    } else if (ts.isImportTypeNode(node) && ts.isLiteralTypeNode(node.argument)) {
      const literal = node.argument.literal;
      if (ts.isStringLiteralLike(literal)) {
        validateModuleSpecifier(literal.text, sourcePath, applicationDirectory);
      }
    } else if (ts.isCallExpression(node)) {
      const isDynamicImport = node.expression.kind === ts.SyntaxKind.ImportKeyword;
      const isRequire = ts.isIdentifier(node.expression) && node.expression.text === "require";
      if (isDynamicImport || isRequire) {
        assert(
          node.arguments.length === 1 && ts.isStringLiteralLike(node.arguments[0]),
          `${sourcePath}: computed module imports are not allowed in an application`,
        );
        validateModuleSpecifier(node.arguments[0].text, sourcePath, applicationDirectory);
      }
    } else if (
      ts.isMetaProperty(node) &&
      node.keywordToken === ts.SyntaxKind.ImportKeyword &&
      node.name.text === "meta"
    ) {
      throw new Error(`${sourcePath}: import.meta loaders are not allowed in an application`);
    }
    ts.forEachChild(node, validateNode);
  }

  validateNode(sourceFile);
}

function validateStylesheetSpecifier(specifier, sourcePath, applicationDirectory) {
  assert(
    (specifier.startsWith("./") || specifier.startsWith("../")) && /\.module\.css$/i.test(specifier),
    `${sourcePath}: composed styles must come from a local .module.css file`,
  );
  assert(
    isInsideDirectory(applicationDirectory, resolve(dirname(sourcePath), specifier)),
    `${sourcePath}: composed stylesheet ${JSON.stringify(specifier)} escapes its application directory`,
  );
}

function validateStylesheetResource(resource, sourcePath, applicationDirectory) {
  if (/^data:/i.test(resource) || resource.startsWith("#")) {
    return;
  }
  assert(
    resource.length > 0 && !resource.startsWith("//") && !/^[A-Za-z][A-Za-z0-9+.-]*:/.test(resource),
    `${sourcePath}: stylesheet resources must use a local relative URL, data URL, or fragment`,
  );

  let resourcePath;
  try {
    const sourceDirectoryUrl = pathToFileURL(`${dirname(sourcePath)}${sep}`);
    resourcePath = fileURLToPath(new URL(resource, sourceDirectoryUrl));
  } catch {
    throw new Error(`${sourcePath}: stylesheet resource ${JSON.stringify(resource)} is invalid`);
  }
  assert(!resourcePath.includes("\0"), `${sourcePath}: stylesheet resource paths cannot contain null bytes`);
  assert(
    isInsideDirectory(applicationDirectory, resourcePath),
    `${sourcePath}: stylesheet resource ${JSON.stringify(resource)} escapes its application directory`,
  );
}

function validateApplicationStylesheet(source, sourcePath, applicationDirectory) {
  let stylesheet;
  try {
    stylesheet = csstree.parse(source, { context: "stylesheet" });
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    throw new Error(`${sourcePath}: invalid CSS: ${detail}`);
  }

  csstree.walk(stylesheet, function validateStylesheetNode(node) {
    if (node.type === "Atrule") {
      const atRule = node.name.toLowerCase();
      if (atRule === "import") {
        throw new Error(`${sourcePath}: CSS @import is not allowed`);
      }
      assert(
        APPLICATION_STYLESHEET_AT_RULES.has(atRule),
        `${sourcePath}: CSS @${atRule} is not allowed in an application module`,
      );
      if (atRule === "keyframes" || atRule === "-webkit-keyframes") {
        const keyframePrelude = node.prelude ? csstree.generate(node.prelude) : "";
        assert(
          !/(?:^|[^A-Za-z0-9_-]):?global(?:\s|\()/i.test(keyframePrelude),
          `${sourcePath}: global keyframe names are not allowed`,
        );
      }
    }

    const containingAtRule = this.atrule?.name.toLowerCase();
    const isKeyframeRule = containingAtRule === "keyframes" || containingAtRule === "-webkit-keyframes";
    if (node.type === "Rule" && node.prelude?.type === "SelectorList" && !isKeyframeRule) {
      for (const selector of node.prelude.children) {
        const first = selector.children.first;
        csstree.walk(selector, (selectorNode) => {
          assert(
            selectorNode.type !== "PseudoClassSelector" || selectorNode.name.toLowerCase() !== "global",
            `${sourcePath}: :global selectors are not allowed`,
          );
          assert(
            selectorNode.type !== "Combinator" || !["+", "~"].includes(selectorNode.name),
            `${sourcePath}: sibling selectors can escape the application root`,
          );
        });
        assert(
          first?.type === "ClassSelector" || first?.type === "IdSelector",
          `${sourcePath}: every selector must start with an application-local class or id`,
        );
      }
    }

    if (node.type === "Declaration" && node.property.toLowerCase() === "composes") {
      const value = csstree.generate(node.value);
      if (/\bfrom\b/i.test(value)) {
        const match = value.match(/\bfrom\s*(?:"([^"]+)"|'([^']+)'|([^\s;]+))\s*$/i);
        assert(match, `${sourcePath}: invalid CSS Modules composes source`);
        validateStylesheetSpecifier(match[1] ?? match[2] ?? match[3], sourcePath, applicationDirectory);
      }
    }

    if (node.type === "Url") {
      validateStylesheetResource(node.value, sourcePath, applicationDirectory);
    }
  });
}

async function validateApplicationImports(applicationDirectory, currentDirectory = applicationDirectory) {
  const entries = await readdir(currentDirectory, { withFileTypes: true });
  for (const entry of entries.sort((left, right) => compareStrings(left.name, right.name))) {
    const entryPath = resolve(currentDirectory, entry.name);
    assert(!entry.isSymbolicLink(), `${entryPath}: symbolic links are not allowed in an application module`);
    if (entry.isDirectory()) {
      await validateApplicationImports(applicationDirectory, entryPath);
      continue;
    }
    if (/\.(?:css|scss|sass|less|styl)$/i.test(entry.name)) {
      assert(entry.name.endsWith(".module.css"), `${entryPath}: application styles must use .module.css`);
      const stylesheet = await readFile(entryPath, "utf8");
      validateApplicationStylesheet(stylesheet, entryPath, applicationDirectory);
      continue;
    }
    if (!/\.(?:[cm]?[jt]sx?)$/.test(entry.name)) {
      continue;
    }
    validateTypeScriptImports(await readFile(entryPath, "utf8"), entryPath, applicationDirectory);
  }
}

export function buildArtifacts(
  applications,
  { applicationsDirectory = DEFAULT_PATHS.applicationsDirectory, frontendOutput = DEFAULT_PATHS.frontendOutput } = {},
) {
  const sorted = [...applications].sort((left, right) => compareStrings(left.manifest.id, right.manifest.id));
  const seenIds = new Set();
  const registrations = [];
  const catalogItems = [];

  for (const application of sorted) {
    const { manifest } = application;
    assert(!seenIds.has(manifest.id), `duplicate application id ${JSON.stringify(manifest.id)}`);
    seenIds.add(manifest.id);
    const contractDigest = digest(manifest);
    registrations.push({
      id: manifest.id,
      version: manifest.version,
      hostApiVersion: manifest.host_api_version,
      contractDigest,
      importPath: relativeImportPath(frontendOutput, applicationsDirectory, manifest.id),
    });
    catalogItems.push({
      id: manifest.id,
      capability_id: `app__${manifest.id}`,
      kind: "app",
      version: manifest.version,
      name: `applications.${manifest.id}.name`,
      description: `applications.${manifest.id}.description`,
      icon: manifest.icon,
      host_api_version: manifest.host_api_version,
      contract_digest: contractDigest,
      service_required: manifest.service_required,
      admin_gated: true,
    });
  }

  const catalogRevision = digest({ schema_version: "1", items: catalogItems });
  const localeResources = buildLocaleResources(sorted);
  const runtimeApplications = catalogItems.map(({ id, service_required }) => ({ id, service_required }));
  return {
    frontend: renderFrontend({ catalogRevision, registrations, localeResources }),
    controlPlane: `${JSON.stringify(
      { schema_version: "1", catalog_revision: catalogRevision, items: catalogItems },
      null,
      2,
    )}\n`,
    runtime: `${JSON.stringify(
      { schema_version: "1", catalog_revision: catalogRevision, applications: runtimeApplications },
      null,
      2,
    )}\n`,
    catalogRevision,
    catalogItems,
    localeResources,
  };
}

function renderFrontend({ catalogRevision, registrations, localeResources }) {
  const registryEntries = registrations
    .map(
      (registration) => `  ${renderJavaScriptKey(registration.id)}: {
    id: ${JSON.stringify(registration.id)},
    version: ${JSON.stringify(registration.version)},
    hostApiVersion: ${JSON.stringify(registration.hostApiVersion)},
    contractDigest: ${JSON.stringify(registration.contractDigest)},
    load: () => import(${JSON.stringify(registration.importPath)}),
  },`,
    )
    .join("\n");

  return `// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// Generated by scripts/generate-applications.mjs. Do not edit by hand.
import type { FredApplicationRegistration } from "@fred/application-host";

export const applicationCatalogRevision = ${JSON.stringify(catalogRevision)};

export const applicationLocaleResources = ${renderJavaScriptValue(localeResources)} as const;

export const applicationRegistry: Readonly<Record<string, FredApplicationRegistration>> = {
${registryEntries}
};
`;
}

function renderJavaScriptValue(value, indentation = 0) {
  if (!isObject(value)) {
    return JSON.stringify(value);
  }

  const entries = Object.entries(value);
  if (entries.length === 0) {
    return "{}";
  }

  const childIndent = " ".repeat(indentation + 2);
  const closingIndent = " ".repeat(indentation);
  const renderedEntries = entries.map(([key, child]) => {
    const renderedKey = renderJavaScriptKey(key);
    const renderedChild = renderJavaScriptValue(child, indentation + 2);
    return `${childIndent}${renderedKey}: ${renderedChild},`;
  });
  return `{\n${renderedEntries.join("\n")}\n${closingIndent}}`;
}

async function writeOrCheck(path, expected, check) {
  if (check) {
    let actual;
    try {
      actual = await readFile(path, "utf8");
    } catch (error) {
      if (error && typeof error === "object" && error.code === "ENOENT") {
        throw new Error(`generated artifact is missing: ${path}`);
      }
      throw error;
    }
    assert(actual === expected, `generated artifact is stale: ${path}`);
    return;
  }

  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, expected, "utf8");
}

export async function generateApplications({
  applicationsDirectory = DEFAULT_PATHS.applicationsDirectory,
  frontendOutput = DEFAULT_PATHS.frontendOutput,
  runtimeOutput = DEFAULT_PATHS.runtimeOutput,
  controlPlaneOutput = DEFAULT_PATHS.controlPlaneOutput,
  check = false,
  includeControlPlane = true,
} = {}) {
  const applications = await discoverApplications(applicationsDirectory);
  const artifacts = buildArtifacts(applications, { applicationsDirectory, frontendOutput });
  await writeOrCheck(frontendOutput, artifacts.frontend, check);
  await writeOrCheck(runtimeOutput, artifacts.runtime, check);
  if (includeControlPlane) {
    await writeOrCheck(controlPlaneOutput, artifacts.controlPlane, check);
  }
  return artifacts;
}

async function main() {
  const args = process.argv.slice(2);
  const unknownArgs = args.filter((arg) => arg !== "--check" && arg !== "--frontend-only");
  assert(unknownArgs.length === 0, `unsupported arguments: ${unknownArgs.join(" ")}`);
  await generateApplications({
    check: args.includes("--check"),
    includeControlPlane: !args.includes("--frontend-only"),
  });
}

const invokedPath = process.argv[1] ? pathToFileURL(resolve(process.argv[1])).href : undefined;
if (invokedPath === import.meta.url) {
  main().catch((error) => {
    const detail = error instanceof Error ? error.message : String(error);
    console.error(`Application manifest generation failed: ${detail}`);
    process.exitCode = 1;
  });
}

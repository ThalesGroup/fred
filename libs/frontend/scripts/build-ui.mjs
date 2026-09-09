import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";
import { copyFile, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";

import react from "@vitejs/plugin-react";
import postcss from "postcss";
import valueParser from "postcss-value-parser";
import { build } from "vite";

import {
  ROOT_LICENSE_PATH,
  UI_COMPONENT_SOURCE_PATHS,
  UI_FONT_SOURCE,
  UI_LICENSE_INPUT_PATH,
  UI_STYLE_SUPPORT_PATHS,
} from "./package-inputs.mjs";
import { inspectMaterialSymbols } from "./inspect-material-symbols.mjs";
import { run } from "./process.mjs";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
export const repositoryRoot = path.resolve(scriptDirectory, "../../..");
export const packageRoot = path.resolve(scriptDirectory, "../ui");
const generatedRoot = path.join(packageRoot, ".generated");
const distributionRoot = path.join(packageRoot, "dist");
const materialIconImportRewrites = new Map(
  [
    "Button/Button.tsx",
    "IconButton/IconButton.tsx",
    "TextInput/TextInput.tsx",
  ].map((componentPath) => [
    `apps/frontend/src/rework/components/shared/atoms/${componentPath}`,
    {
      from: 'import Icon, { IconProps } from "../Icon/Icon.tsx";',
      to: 'import { MaterialIcon as Icon, type MaterialIconProps as IconProps } from "../Icon/Icon.tsx";',
    },
  ]),
);
const generatedIconPath =
  "apps/frontend/src/rework/components/shared/atoms/Icon/Icon.tsx";
const generatedTypePath =
  "apps/frontend/src/rework/components/shared/utils/Type.ts";
export const UI_RUNTIME_SOURCE_PATHS = UI_COMPONENT_SOURCE_PATHS.filter(
  (sourcePath) => sourcePath !== generatedTypePath,
);

function sha256(content) {
  return createHash("sha256").update(content).digest("hex");
}

async function copyCanonical(relativePath) {
  const target = path.join(
    generatedRoot,
    path.relative("apps/frontend", relativePath),
  );
  await mkdir(path.dirname(target), { recursive: true });
  await copyFile(path.join(repositoryRoot, relativePath), target);
  let generated = await readFile(target, "utf8");
  const rewrite = materialIconImportRewrites.get(relativePath);
  if (rewrite) {
    assert.equal(
      generated.split(rewrite.from).length - 1,
      1,
      `canonical material-icon import changed in ${relativePath}`,
    );
    generated = generated.replace(rewrite.from, rewrite.to);
  }
  if (relativePath === generatedIconPath) {
    const broadImport =
      'import { IconCategory, IconType, isCustomIcon, MaterialIconType } from "../../utils/Type.ts";';
    const materialImport =
      'import { MaterialIconType } from "../../utils/Type.ts";';
    assert(generated.includes(broadImport), "canonical Icon imports changed");
    generated = generated.replace(broadImport, materialImport);
    const broadPropsStart = generated.indexOf("export interface IconProps");
    const materialPropsStart = generated.indexOf(
      "export interface MaterialIconProps",
    );
    const wrapperStart = generated.indexOf("export default function Icon");
    assert(
      broadPropsStart > 0 &&
        materialPropsStart > broadPropsStart &&
        wrapperStart > materialPropsStart,
      "canonical Icon boundary changed",
    );
    generated =
      generated.slice(0, broadPropsStart) + generated.slice(materialPropsStart);
    const narrowedWrapperStart = generated.indexOf(
      "export default function Icon",
    );
    generated = `${generated.slice(0, narrowedWrapperStart).trimEnd()}\n`;
  }
  if (relativePath === generatedTypePath) {
    const applicationIconTypes =
      'export type IconCategory = "outlined" | "rounded" | "sharp";\n\nconst customIcons = ["customAgent"] as const;\n\n';
    const materialType =
      "export type MaterialIconType = (typeof materialIcons)[number];";
    assert(
      generated.includes(applicationIconTypes),
      "canonical application icon types changed",
    );
    generated = generated.replace(applicationIconTypes, "");
    const materialTypeEnd =
      generated.indexOf(materialType) + materialType.length;
    assert(
      materialTypeEnd >= materialType.length,
      "canonical MaterialIconType changed",
    );
    generated = `${generated.slice(0, materialTypeEnd)}\n`;
  }
  await writeFile(target, generated);
}

async function buildMaterialBaseCss() {
  const stylesheetPath = path.join(
    repositoryRoot,
    "apps/frontend/src/styles/index.css",
  );
  const stylesheet = postcss.parse(await readFile(stylesheetPath, "utf8"), {
    from: stylesheetPath,
  });
  const output = postcss.root();
  const faces = [];
  stylesheet.walkAtRules("font-face", (rule) => {
    let family;
    rule.walkDecls("font-family", (declaration) => {
      family = declaration.value.replace(/["']/g, "");
    });
    if (family !== "Material Symbols Outlined") return;
    const clone = rule.clone();
    clone.walkDecls("src", (declaration) => {
      const parsed = valueParser(declaration.value);
      parsed.walk((node) => {
        if (node.type === "function" && node.value.toLowerCase() === "url") {
          node.nodes = [
            {
              type: "string",
              quote: '"',
              value: `./assets/${UI_FONT_SOURCE.packedName}?no-inline`,
            },
          ];
        }
      });
      declaration.value = parsed.toString();
    });
    faces.push(clone);
  });
  if (faces.length !== 1)
    throw new Error(
      `Expected one canonical Material Symbols Outlined face, found ${faces.length}`,
    );
  const rules = [];
  stylesheet.walkRules(".material-symbols-outlined", (rule) => {
    const clone = rule.clone();
    clone.selector = ".fred-ui .material-symbols-outlined";
    rules.push(clone);
  });
  if (rules.length !== 1)
    throw new Error(
      `Expected one canonical Material Symbols Outlined rule, found ${rules.length}`,
    );
  output.append(faces[0], rules[0]);
  output.append(
    postcss.parse(
      ".fred-ui, .fred-ui *, .fred-ui *::before, .fred-ui *::after { box-sizing: border-box; }",
    ),
  );
  return `${output.toString()}\n`;
}

function moduleEvidencePlugin(evidence) {
  return {
    name: "fred-ui-build-evidence",
    generateBundle(_options, bundle) {
      evidence.modules = [...this.getModuleIds()]
        .map((id) => ({
          id: (path.isAbsolute(id) ? path.relative(repositoryRoot, id) : id)
            .split(path.sep)
            .join("/"),
          external: this.getModuleInfo(id)?.isExternal ?? false,
        }))
        .filter(({ id }) => !id.startsWith("../"))
        .sort((left, right) => left.id.localeCompare(right.id));
      evidence.outputs = Object.keys(bundle).sort();
    },
  };
}

export function assertUiBuildSourceGraph(
  modules,
  expectedSources = UI_RUNTIME_SOURCE_PATHS,
) {
  const consumed = modules
    .filter(
      ({ id, external }) => id.includes("ui/.generated/src/") && !external,
    )
    .map(({ id }) =>
      id.replace(
        /^libs\/frontend\/ui\/\.generated\/src\//,
        "apps/frontend/src/",
      ),
    )
    .sort();
  const expected = [...expectedSources].sort();
  assert.deepEqual(
    consumed,
    expected,
    "UI build source graph differs from the canonical allowlist",
  );
}

export function isUiExternal(id) {
  return (
    id === "react" ||
    id.startsWith("react/") ||
    id === "react-dom" ||
    id.startsWith("react-dom/")
  );
}

export async function buildUi() {
  await Promise.all([
    rm(generatedRoot, { recursive: true, force: true }),
    rm(distributionRoot, { recursive: true, force: true }),
    rm(path.join(packageRoot, "LICENSE"), { force: true }),
    rm(path.join(packageRoot, "licenses"), { recursive: true, force: true }),
    rm(path.join(packageRoot, "build-evidence.json"), { force: true }),
  ]);
  await mkdir(generatedRoot, { recursive: true });
  await Promise.all(
    [...UI_COMPONENT_SOURCE_PATHS, ...UI_STYLE_SUPPORT_PATHS].map(
      copyCanonical,
    ),
  );
  await writeFile(
    path.join(generatedRoot, "style-modules.d.ts"),
    'declare module "*.module.css" { const classes: Record<string, string>; export default classes; }\ndeclare module "*.module.scss" { const classes: Record<string, string>; export default classes; }\n',
  );

  const canonicalFont = path.join(repositoryRoot, UI_FONT_SOURCE.sourcePath);
  const glyphEvidence = await inspectMaterialSymbols({
    fontPath: canonicalFont,
  });
  await mkdir(path.join(generatedRoot, "assets"), { recursive: true });
  await copyFile(
    canonicalFont,
    path.join(generatedRoot, "assets", UI_FONT_SOURCE.packedName),
  );
  await writeFile(
    path.join(generatedRoot, "base.css"),
    await buildMaterialBaseCss(),
  );

  const buildEvidence = {
    sourceAllowlist: [...UI_COMPONENT_SOURCE_PATHS, ...UI_STYLE_SUPPORT_PATHS],
    externals: ["react", "react/*", "react-dom", "react-dom/*"],
    glyphs: glyphEvidence,
  };
  await build({
    configFile: false,
    base: "./",
    root: packageRoot,
    plugins: [react(), moduleEvidencePlugin(buildEvidence)],
    css: { preprocessorOptions: { scss: { loadPaths: [generatedRoot] } } },
    build: {
      emptyOutDir: true,
      lib: {
        entry: path.join(packageRoot, "src/index.tsx"),
        formats: ["es"],
        fileName: () => "index.js",
      },
      rollupOptions: {
        external: isUiExternal,
        output: {
          assetFileNames: (asset) =>
            asset.name?.endsWith(".css")
              ? "styles.css"
              : "fonts/MaterialSymbolsOutlined.woff2",
        },
      },
    },
  });
  assertUiBuildSourceGraph(buildEvidence.modules);
  await run("npm", ["exec", "--", "tsc", "-p", "ui/tsconfig.json"], {
    cwd: path.dirname(packageRoot),
  });
  const publicDeclarationsPath = path.join(
    distributionRoot,
    "types/src/index.d.ts",
  );
  const publicDeclarations = await readFile(publicDeclarationsPath, "utf8");
  await writeFile(
    publicDeclarationsPath,
    publicDeclarations.replace('import "../.generated/base.css";\n', ""),
  );

  const licenseRoot = path.join(packageRoot, "licenses");
  await mkdir(licenseRoot, { recursive: true });
  await Promise.all([
    copyFile(
      path.join(repositoryRoot, ROOT_LICENSE_PATH),
      path.join(packageRoot, "LICENSE"),
    ),
    copyFile(
      path.join(repositoryRoot, UI_LICENSE_INPUT_PATH),
      path.join(licenseRoot, "Material-Symbols-Apache-2.0.txt"),
    ),
  ]);
  const license = await readFile(
    path.join(licenseRoot, "Material-Symbols-Apache-2.0.txt"),
  );
  buildEvidence.licenseSha256 = sha256(license);
  buildEvidence.outputImports = [
    ...new Set(
      (await readFile(path.join(distributionRoot, "index.js"), "utf8")).match(
        /from\s+["']([^"']+)["']/g,
      ) ?? [],
    ),
  ];
  const javascript = await readFile(
    path.join(distributionRoot, "index.js"),
    "utf8",
  );
  for (const forbidden of [
    "customAgent",
    "material-symbols-rounded",
    "material-symbols-sharp",
    "/images/icons/",
  ])
    assert(
      !javascript.includes(forbidden),
      `UI JavaScript retained application-only icon behavior: ${forbidden}`,
    );
  await writeFile(
    path.join(packageRoot, "build-evidence.json"),
    `${JSON.stringify(buildEvidence, null, 2)}\n`,
  );
  return buildEvidence;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  process.stdout.write(`${JSON.stringify(await buildUi(), null, 2)}\n`);
}

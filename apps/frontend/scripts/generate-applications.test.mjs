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

import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { afterEach, describe, test } from "node:test";

import {
  buildArtifacts,
  discoverApplications,
  generateApplications,
  validateManifest,
} from "./generate-applications.mjs";

const temporaryDirectories = [];

afterEach(async () => {
  await Promise.all(temporaryDirectories.splice(0).map((path) => rm(path, { recursive: true, force: true })));
});

async function createWorkspace() {
  const root = await mkdtemp(resolve(tmpdir(), "fred-app-generator-"));
  temporaryDirectories.push(root);
  return {
    root,
    applicationsDirectory: resolve(root, "applications"),
    frontendOutput: resolve(root, "generated/applicationRegistry.ts"),
    runtimeOutput: resolve(root, "generated/application-runtime.json"),
    controlPlaneOutput: resolve(root, "generated/catalog.generated.json"),
  };
}

function manifest(overrides = {}) {
  return {
    schema_version: "1",
    id: "example",
    version: "1.0.0",
    display_name: { en: "Placeholder App", fr: "Application temporaire" },
    description: { en: "Placeholder application." },
    host_api_version: "1",
    module_key: "example",
    service_required: false,
    ...overrides,
  };
}

async function installApplication(applicationsDirectory, directoryName, content) {
  const directory = resolve(applicationsDirectory, directoryName);
  const frontendDirectory = resolve(directory, "frontend");
  await mkdir(frontendDirectory, { recursive: true });
  await writeFile(resolve(directory, "fred-app.json"), `${JSON.stringify(content, null, 2)}\n`, "utf8");
  await writeFile(resolve(frontendDirectory, "index.tsx"), "export default function App() { return null; }\n", "utf8");
}

describe("application manifest generation", () => {
  test("emits matching deterministic frontend and control-plane artifacts", async () => {
    const workspace = await createWorkspace();
    await installApplication(workspace.applicationsDirectory, "example", manifest());

    const first = await generateApplications(workspace);
    const second = await generateApplications(workspace);
    await generateApplications({ ...workspace, check: true });

    assert.equal(first.frontend, second.frontend);
    assert.equal(first.controlPlane, second.controlPlane);
    assert.equal(first.runtime, second.runtime);
    const catalog = JSON.parse(await readFile(workspace.controlPlaneOutput, "utf8"));
    assert.equal(catalog.catalog_revision, first.catalogRevision);
    assert.equal(catalog.items[0].contract_digest, first.catalogItems[0].contract_digest);
    assert.equal(catalog.items[0].capability_id, "app__example");
    assert.equal(catalog.items[0].service_required, false);
    const runtime = JSON.parse(await readFile(workspace.runtimeOutput, "utf8"));
    assert.equal(runtime.catalog_revision, catalog.catalog_revision);
    assert.deepEqual(runtime.applications, [{ id: "example", service_required: false }]);
    assert.match(first.frontend, /load: \(\) => import\("\.\.\/applications\/example\/frontend\/index\.tsx"\)/);
    assert.equal(first.localeResources.fr.applications.example.description, "Placeholder application.");
  });

  test("defaults a missing icon and missing localized text to safe fallbacks", () => {
    const normalized = validateManifest(manifest({ display_name: { en: "Placeholder App" } }));
    assert.equal(normalized.icon, "extension");
    assert.equal(validateManifest(manifest({ icon: "architecture" })).icon, "architecture");

    const artifacts = buildArtifacts([{ directoryName: "example", manifest: normalized }], {
      applicationsDirectory: "/applications",
      frontendOutput: "/generated/applicationRegistry.ts",
    });
    assert.equal(artifacts.localeResources.fr.applications.example.description, "Placeholder application.");
    assert.deepEqual(Object.keys(buildArtifacts([]).localeResources), ["en", "fr"]);
  });

  test("rejects unsafe, incomplete, or incompatible manifests", () => {
    const invalid = [
      [manifest({ schema_version: "2" }), /schema_version/],
      [manifest({ id: "Bad Id", module_key: "Bad Id" }), /lowercase slug/],
      [manifest({ id: "constructor", module_key: "constructor" }), /is reserved/],
      [manifest({ version: "latest" }), /semantic version/],
      [manifest({ version: "1.0.0-01" }), /semantic version/],
      [manifest({ display_name: { fr: "Sans repli" } }), /English fallback/],
      [manifest({ display_name: { en: "Example", not_a_locale: "Invalid" } }), /invalid locale/],
      [manifest({ icon: "<svg>" }), /icon must be one of/],
      [manifest({ module_key: "https://modules.example/app.js" }), /module_key must match/],
      [manifest({ module_url: "https://modules.example/app.js" }), /unsupported field/],
      [manifest({ description: { en: "<script>alert(1)</script>" } }), /raw HTML/],
      [manifest({ host_api_version: "2" }), /unsupported host_api_version/],
      [manifest({ service_required: "false" }), /service_required must be a boolean/],
    ];

    for (const [candidate, expected] of invalid) {
      assert.throws(() => validateManifest(candidate), expected);
    }
    assert.throws(() => validateManifest(manifest(), { directoryName: "different" }), /must match directory/);
  });

  test("rejects duplicate application ids defensively", () => {
    const normalized = validateManifest(manifest());
    assert.throws(
      () =>
        buildArtifacts([
          { directoryName: "example", manifest: normalized },
          { directoryName: "example-copy", manifest: normalized },
        ]),
      /duplicate application id/,
    );
  });

  test("changes only the updated application's contract digest", () => {
    const example = validateManifest(manifest());
    const second = validateManifest(
      manifest({
        id: "second",
        module_key: "second",
        display_name: { en: "Second App" },
        description: { en: "Second placeholder application." },
      }),
    );
    const before = buildArtifacts([
      { directoryName: "example", manifest: example },
      { directoryName: "second", manifest: second },
    ]);
    const after = buildArtifacts([
      { directoryName: "example", manifest: example },
      {
        directoryName: "second",
        manifest: validateManifest({ ...second, version: "1.1.0" }),
      },
    ]);

    assert.equal(before.catalogItems[0].contract_digest, after.catalogItems[0].contract_digest);
    assert.notEqual(before.catalogItems[1].contract_digest, after.catalogItems[1].contract_digest);
    assert.notEqual(before.catalogRevision, after.catalogRevision);
  });

  test("check mode fails when any generated artifact is stale or absent", async () => {
    const workspace = await createWorkspace();
    await installApplication(workspace.applicationsDirectory, "example", manifest());
    await generateApplications(workspace);
    await writeFile(workspace.frontendOutput, "stale\n", "utf8");

    await assert.rejects(generateApplications({ ...workspace, check: true }), /generated artifact is stale/);
    await rm(workspace.frontendOutput);
    await assert.rejects(generateApplications({ ...workspace, check: true }), /generated artifact is missing/);

    await generateApplications(workspace);
    await writeFile(workspace.runtimeOutput, "stale\n", "utf8");
    await assert.rejects(generateApplications({ ...workspace, check: true }), /generated artifact is stale/);
  });

  test("frontend-only checks do not require a control-plane checkout", async () => {
    const workspace = await createWorkspace();
    await installApplication(workspace.applicationsDirectory, "example", manifest());
    await generateApplications({ ...workspace, includeControlPlane: false });

    await generateApplications({ ...workspace, check: true, includeControlPlane: false });
    await assert.rejects(
      generateApplications({ ...workspace, check: true, includeControlPlane: true }),
      /generated artifact is missing/,
    );
  });

  test("discovery requires a matching module at the installation boundary", async () => {
    const workspace = await createWorkspace();
    const directory = resolve(workspace.applicationsDirectory, "example");
    await mkdir(directory, { recursive: true });
    await writeFile(resolve(directory, "fred-app.json"), JSON.stringify(manifest()), "utf8");

    await assert.rejects(discoverApplications(workspace.applicationsDirectory), /missing frontend\/index\.tsx/);
  });

  test("rejects a symbolic link as the application frontend root", async () => {
    const workspace = await createWorkspace();
    const applicationDirectory = resolve(workspace.applicationsDirectory, "example");
    const backendDirectory = resolve(applicationDirectory, "backend");
    await mkdir(backendDirectory, { recursive: true });
    await writeFile(resolve(applicationDirectory, "fred-app.json"), JSON.stringify(manifest()), "utf8");
    await writeFile(resolve(backendDirectory, "index.tsx"), "export default function App() { return null; }\n", "utf8");
    await symlink(backendDirectory, resolve(applicationDirectory, "frontend"), "dir");

    await assert.rejects(discoverApplications(workspace.applicationsDirectory), /frontend must be a regular directory/);
  });

  test("allows React, the public host facade, and relative imports contained within one application", async () => {
    const workspace = await createWorkspace();
    await installApplication(workspace.applicationsDirectory, "example", manifest());
    const applicationDirectory = resolve(workspace.applicationsDirectory, "example");
    const frontendDirectory = resolve(applicationDirectory, "frontend");
    await mkdir(resolve(frontendDirectory, "components"), { recursive: true });
    await writeFile(
      resolve(frontendDirectory, "index.tsx"),
      `import React from "react";
import type { FredApplicationPageProps } from "@fred/application-host";
import { exampleLabel } from "./components/ExampleLabel";
import "./example.module.css";

export default function App(_props: FredApplicationPageProps) {
  return React.createElement("span", null, exampleLabel);
}
`,
      "utf8",
    );
    await writeFile(
      resolve(frontendDirectory, "components/ExampleLabel.ts"),
      `export { exampleLabel } from "../shared";
`,
      "utf8",
    );
    await writeFile(resolve(frontendDirectory, "shared.ts"), 'export const exampleLabel = "Example";\n', "utf8");
    await writeFile(resolve(frontendDirectory, "example.module.css"), ".example { display: block; }\n", "utf8");

    await assert.doesNotReject(discoverApplications(workspace.applicationsDirectory));
  });

  test("rejects private Fred, third-party, cross-application, and computed imports", async () => {
    const workspace = await createWorkspace();
    await installApplication(workspace.applicationsDirectory, "example", manifest());
    const modulePath = resolve(workspace.applicationsDirectory, "example/frontend/index.tsx");
    const invalidSources = [
      ['import "src/rework/private";\nexport default function App() { return null; }\n', /outside the React/],
      ['import "@reduxjs/toolkit";\nexport default function App() { return null; }\n', /outside the React/],
      ['import "../another-app/index";\nexport default function App() { return null; }\n', /escapes its application/],
      ['import "../backend/service";\nexport default function App() { return null; }\n', /escapes its application/],
      [
        'const moduleName = "./local";\nvoid import(moduleName);\nexport default function App() { return null; }\n',
        /computed module imports are not allowed/,
      ],
      [
        'const modules = import.meta.glob("/src/rework/private/**/*.tsx");\nexport default function App() { return modules; }\n',
        /import\.meta loaders are not allowed/,
      ],
      ['import "./global.css";\nexport default function App() { return null; }\n', /must use a local \.module\.css/],
    ];

    for (const [source, expected] of invalidSources) {
      await writeFile(modulePath, source, "utf8");
      await assert.rejects(discoverApplications(workspace.applicationsDirectory), expected);
    }
  });

  test("rejects CSS-module escapes and external stylesheet imports", async () => {
    const workspace = await createWorkspace();
    await installApplication(workspace.applicationsDirectory, "example", manifest());
    const stylesheet = resolve(workspace.applicationsDirectory, "example/frontend/Example.module.css");

    for (const [source, expected] of [
      [":global(body) { margin: 0; }\n", /:global selectors are not allowed/],
      ['@import url("https://styles.example/theme.css");\n.page { display: block; }\n', /CSS @import is not allowed/],
      ["body { margin: 0; }\n", /every selector must start with an application-local class or id/],
      [":root { --app-color: red; }\n", /every selector must start with an application-local class or id/],
      ["* { box-sizing: border-box; }\n", /every selector must start with an application-local class or id/],
      [".page + button { display: none; }\n", /sibling selectors can escape/],
      [
        '.page { composes: private from "../../../src/private.module.css"; }\n',
        /composed stylesheet .* escapes its application directory/,
      ],
      [
        '.page { background-image: url("../../../src/private.svg"); }\n',
        /stylesheet resource .* escapes its application directory/,
      ],
      [
        '.page { background-image: url("https://styles.example/private.svg"); }\n',
        /stylesheet resources must use a local relative URL/,
      ],
      ["@page { margin: 0; }\n", /CSS @page is not allowed/],
      [
        '@property --fred-color { syntax: "<color>"; inherits: true; initial-value: red; }\n',
        /CSS @property is not allowed/,
      ],
      ['@font-face { font-family: "Private"; src: url("./font.woff2"); }\n', /CSS @font-face is not allowed/],
      [
        "@keyframes :global(fade) { from { opacity: 0; } to { opacity: 1; } }\n",
        /global keyframe names are not allowed/,
      ],
      [
        "@keyframes global(fade) { from { opacity: 0; } to { opacity: 1; } }\n",
        /global keyframe names are not allowed/,
      ],
    ]) {
      await writeFile(stylesheet, source, "utf8");
      await assert.rejects(discoverApplications(workspace.applicationsDirectory), expected);
    }

    await writeFile(
      stylesheet,
      '@media (min-width: 1px) { .page button { background-image: url("./icon.svg"); mask-image: url("#mask"); } }\n@keyframes appPulse { from { opacity: 0; } to { opacity: 1; } }\n.shared { composes: page from "./Example.module.css"; background-image: url("data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=="); }\n',
      "utf8",
    );
    await writeFile(resolve(workspace.applicationsDirectory, "example/frontend/icon.svg"), "<svg></svg>\n", "utf8");
    await assert.doesNotReject(discoverApplications(workspace.applicationsDirectory));
  });

  test("keeps backend implementation outside the frontend validation boundary", async () => {
    const workspace = await createWorkspace();
    await installApplication(workspace.applicationsDirectory, "example", manifest());
    const backendDirectory = resolve(workspace.applicationsDirectory, "example/backend");
    await mkdir(backendDirectory, { recursive: true });
    await writeFile(resolve(backendDirectory, "service.ts"), 'import "backend-library";\n', "utf8");

    await assert.doesNotReject(discoverApplications(workspace.applicationsDirectory));

    await writeFile(
      resolve(workspace.applicationsDirectory, "example/frontend/index.tsx"),
      'import "../backend/service";\nexport default function App() { return null; }\n',
      "utf8",
    );
    await assert.rejects(discoverApplications(workspace.applicationsDirectory), /escapes its application/);
  });

  test("does not interpret comments or ordinary strings as module imports", async () => {
    const workspace = await createWorkspace();
    await installApplication(workspace.applicationsDirectory, "example", manifest());
    await writeFile(
      resolve(workspace.applicationsDirectory, "example/frontend/index.tsx"),
      `// import "src/rework/private";
const example = 'require("@reduxjs/toolkit")';
export default function App() { return example; }
`,
      "utf8",
    );

    await assert.doesNotReject(discoverApplications(workspace.applicationsDirectory));
  });
});

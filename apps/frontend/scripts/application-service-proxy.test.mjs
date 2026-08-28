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
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { afterEach, describe, test } from "node:test";

import {
  loadApplicationServiceProxyConfig,
  parseApplicationServicesEnabled,
  rewriteApplicationServicePath,
} from "./application-service-proxy.mjs";

const temporaryDirectories = [];

afterEach(async () => {
  await Promise.all(temporaryDirectories.splice(0).map((path) => rm(path, { recursive: true, force: true })));
});

async function runtimeContract(applications) {
  const directory = await mkdtemp(resolve(tmpdir(), "fred-app-proxy-"));
  temporaryDirectories.push(directory);
  const contractPath = resolve(directory, "application-runtime.json");
  await writeFile(
    contractPath,
    JSON.stringify({
      schema_version: "1",
      catalog_revision: `sha256:${"a".repeat(64)}`,
      applications,
    }),
    "utf8",
  );
  return contractPath;
}

describe("application service proxy configuration", () => {
  test("defaults disabled without reading application contracts or mappings", () => {
    const config = loadApplicationServiceProxyConfig({
      contractPath: "/missing/application-runtime.json",
      mappingsJson: "not-json",
    });

    assert.deepEqual(config.proxy, {});
    assert.equal(config.classifyRequest("/ordinary-page"), null);
    assert.equal(config.classifyRequest("/app-services"), 404);
    assert.equal(config.classifyRequest("/app-services/example/teams/team-a?query=true"), 404);
    assert.equal(config.classifyRequest("/app-services-extra/example"), null);
  });

  test("accepts only explicit boolean feature configuration", () => {
    assert.equal(parseApplicationServicesEnabled(undefined), false);
    assert.equal(parseApplicationServicesEnabled(""), false);
    assert.equal(parseApplicationServicesEnabled("false"), false);
    assert.equal(parseApplicationServicesEnabled("true"), true);
    assert.throws(() => parseApplicationServicesEnabled("TRUE"), /must be either true or false/);
    assert.throws(
      () =>
        loadApplicationServiceProxyConfig({
          contractPath: "/missing/application-runtime.json",
          enabled: "true",
        }),
      /enabled must be a boolean/,
    );
  });

  test("normalizes upstream roots and strips only the application prefix", async () => {
    const contractPath = await runtimeContract([{ id: "example-app", service_required: true }]);
    const config = loadApplicationServiceProxyConfig({
      contractPath,
      mappingsJson: JSON.stringify({ "example-app": "http://service.invalid/base///" }),
      enabled: true,
    });

    const route = config.proxy["/app-services/example-app"];
    assert.equal(route.target, "http://service.invalid/base");
    assert.equal(route.changeOrigin, true);
    assert.equal(route.secure, true);
    assert.equal(
      route.rewrite("/app-services/example-app/teams/team-a/items/one?view=full"),
      "/teams/team-a/items/one?view=full",
    );
    assert.equal(config.classifyRequest("/app-services/example-app/teams/team-a"), "proxy");
  });

  test("fails closed for unknown ids and reports an installed service without a mapping as unavailable", async () => {
    const contractPath = await runtimeContract([{ id: "optional-app", service_required: false }]);
    const config = loadApplicationServiceProxyConfig({ contractPath, enabled: true });

    assert.equal(config.classifyRequest("/ordinary-page"), null);
    assert.equal(config.classifyRequest("/app-services/unknown/teams/team-a"), 404);
    assert.equal(config.classifyRequest("/app-services/optional-app/teams/team-a"), 503);
    assert.equal(config.classifyRequest("/app-services/optional-app-else/teams/team-a"), 404);
    assert.equal(config.classifyRequest("/app-services"), 404);
  });

  test("requires one mapping for every service_required application", async () => {
    const contractPath = await runtimeContract([
      { id: "required-app", service_required: true },
      { id: "optional-app", service_required: false },
    ]);

    assert.throws(
      () => loadApplicationServiceProxyConfig({ contractPath, enabled: true }),
      /service_required application "required-app" has no upstream mapping/,
    );
    assert.doesNotThrow(() =>
      loadApplicationServiceProxyConfig({ contractPath, requireRequiredMappings: false, enabled: true }),
    );
  });

  test("rejects uninstalled mappings and unsafe upstream URLs", async () => {
    const contractPath = await runtimeContract([{ id: "example-app", service_required: false }]);
    const invalidMappings = [
      [{ unknown: "http://service.invalid" }, /uninstalled application/],
      [{ "example-app": "file:///tmp/service" }, /safe HTTP\(S\) URL/],
      [{ "example-app": ["http://", "placeholder", ":", "value", "@service.invalid"].join("") }, /without credentials/],
      [{ "example-app": "http://service.invalid/path?parameter=value" }, /without credentials or query/],
      [{ "example-app": "http://service.invalid/$variable" }, /safe HTTP\(S\) URL/],
      [{ "example-app": "http://service.invalid:99999" }, /safe HTTP\(S\) URL/],
      [{ "example-app": "http://service.invalid/root/../private" }, /safe HTTP\(S\) URL/],
      [{ "example-app": "http://service.invalid/%2e%2e/private" }, /safe HTTP\(S\) URL/],
    ];

    for (const [mapping, expected] of invalidMappings) {
      assert.throws(
        () => loadApplicationServiceProxyConfig({ contractPath, mappingsJson: JSON.stringify(mapping), enabled: true }),
        expected,
      );
    }
  });

  test("rejects malformed contracts and path/id prefix confusion", async () => {
    const duplicateContract = await runtimeContract([
      { id: "example-app", service_required: false },
      { id: "example-app", service_required: false },
    ]);
    assert.throws(
      () => loadApplicationServiceProxyConfig({ contractPath: duplicateContract, enabled: true }),
      /duplicate/,
    );
    assert.throws(
      () => rewriteApplicationServicePath("/app-services/example-app-extra/teams/team-a", "example-app"),
      /does not belong/,
    );
  });
});

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
import { describe, test } from "node:test";

import {
  loadApplicationProxyConfig,
  parseApplicationRegistrations,
  parseApplicationsEnabled,
  rewriteApplicationServicePath,
  rewriteApplicationUiPath,
} from "./application-proxy.mjs";

function registrations(entries) {
  return JSON.stringify(entries);
}

// Vite resolves server.proxy keys itself: a "^" key is matched as a RegExp
// against the whole request url, any other key with url.startsWith, first
// inserted match winning (vite 6, doesProxyContextMatchUrl in proxy.ts).
function resolveThroughViteProxy(proxy, requestUrl) {
  for (const context of Object.keys(proxy)) {
    if ((context[0] === "^" && new RegExp(context).test(requestUrl)) || requestUrl.startsWith(context)) {
      return proxy[context];
    }
  }
  return null;
}

describe("application proxy configuration", () => {
  test("defaults disabled and refuses both namespaces without reading configuration", () => {
    const config = loadApplicationProxyConfig({ registrationsJson: "not-json" });

    assert.deepEqual(config.proxy, {});
    assert.equal(config.classifyRequest("/ordinary-page"), null);
    assert.equal(config.classifyRequest("/apps"), 404);
    assert.equal(config.classifyRequest("/apps/example/index.html"), 404);
    assert.equal(config.classifyRequest("/app-services"), 404);
    assert.equal(config.classifyRequest("/app-services/example/teams/team-a?query=true"), 404);
    assert.equal(config.classifyRequest("/apps-extra/example"), null);
    assert.equal(config.classifyRequest("/app-services-extra/example"), null);
  });

  test("accepts only explicit boolean feature configuration", () => {
    assert.equal(parseApplicationsEnabled(undefined), false);
    assert.equal(parseApplicationsEnabled(""), false);
    assert.equal(parseApplicationsEnabled("false"), false);
    assert.equal(parseApplicationsEnabled("true"), true);
    assert.throws(() => parseApplicationsEnabled("TRUE"), /must be either true or false/);
    assert.throws(() => loadApplicationProxyConfig({ enabled: "true" }), /enabled must be a boolean/);
  });

  test("keeps the /apps prefix upstream and strips only the /app-services prefix", () => {
    const config = loadApplicationProxyConfig({
      registrationsJson: registrations([
        {
          app_id: "example-app",
          ui_upstream: "http://ui.invalid///",
          service_upstream: "http://service.invalid///",
          service_required: true,
        },
      ]),
      enabled: true,
    });

    const ui = resolveThroughViteProxy(config.proxy, "/apps/example-app/assets/main.js");
    assert.equal(ui.target, "http://ui.invalid");
    assert.equal(ui.changeOrigin, true);
    assert.equal(ui.secure, true);
    assert.equal(ui.rewrite("/apps/example-app/assets/main.js"), "/apps/example-app/assets/main.js");
    assert.equal(
      resolveThroughViteProxy(config.proxy, "/apps/example-app").rewrite("/apps/example-app"),
      "/apps/example-app",
    );

    const service = resolveThroughViteProxy(config.proxy, "/app-services/example-app/teams/team-a/items/one?view=full");
    assert.equal(service.target, "http://service.invalid");
    assert.equal(
      service.rewrite("/app-services/example-app/teams/team-a/items/one?view=full"),
      "/teams/team-a/items/one?view=full",
    );

    assert.equal(config.classifyRequest("/apps/example-app/"), "proxy");
    assert.equal(config.classifyRequest("/apps/example-app"), "proxy");
    assert.equal(config.classifyRequest("/app-services/example-app/teams/team-a"), "proxy");
  });

  test("reports a registered application without a service upstream as unavailable, not missing", () => {
    const config = loadApplicationProxyConfig({
      registrationsJson: registrations([{ app_id: "ui-only-app", ui_upstream: "http://ui.invalid" }]),
      enabled: true,
    });

    assert.equal(config.classifyRequest("/ordinary-page"), null);
    assert.equal(config.classifyRequest("/app-services/ui-only-app/teams/team-a"), 503);
    assert.equal(config.classifyRequest("/app-services/unknown/teams/team-a"), 404);
    assert.equal(config.classifyRequest("/app-services"), 404);
    assert.equal(resolveThroughViteProxy(config.proxy, "/app-services/ui-only-app/teams/team-a"), null);
    // The UI half of a service-free application still resolves.
    assert.equal(config.classifyRequest("/apps/ui-only-app/"), "proxy");
    assert.equal(config.classifyRequest("/apps/unknown/"), 404);
    assert.equal(config.classifyRequest("/apps"), 404);
  });

  test("refuses id prefix confusion in both namespaces", () => {
    const config = loadApplicationProxyConfig({
      registrationsJson: registrations([
        { app_id: "example-app", ui_upstream: "http://ui.invalid", service_upstream: "http://service.invalid" },
      ]),
      enabled: true,
    });

    assert.equal(config.classifyRequest("/apps/example-app-else/index.html"), 404);
    assert.equal(config.classifyRequest("/app-services/example-app-else/teams/team-a"), 404);
    assert.throws(
      () => rewriteApplicationUiPath("/apps/example-app-else/index.html", "example-app"),
      /does not belong/,
    );
    assert.throws(
      () => rewriteApplicationServicePath("/app-services/example-app-extra/teams/team-a", "example-app"),
      /does not belong/,
    );
  });

  test("requires a service upstream for every service_required application", () => {
    const registrationsJson = registrations([
      { app_id: "required-app", ui_upstream: "http://ui.invalid", service_required: true },
      { app_id: "optional-app", ui_upstream: "http://ui.invalid" },
    ]);

    assert.throws(
      () => loadApplicationProxyConfig({ registrationsJson, enabled: true }),
      /service_required application "required-app" has no service_upstream/,
    );
    assert.doesNotThrow(() =>
      loadApplicationProxyConfig({ registrationsJson, requireServiceUpstreams: false, enabled: true }),
    );
  });

  test("rejects unsafe upstream URLs on both the ui and service legs", () => {
    const unsafe = [
      "file:///tmp/service",
      ["http://", "placeholder", ":", "value", "@service.invalid"].join(""),
      "http://service.invalid/path?parameter=value",
      "http://service.invalid/$variable",
      "http://service.invalid:99999",
      "http://service.invalid/root/../private",
      "http://service.invalid/%2e%2e/private",
      // An upstream base path is not prefixed onto the request path, it
      // replaces it, so every application request would collapse onto it.
      "http://service.invalid/base",
      "http://service.invalid/base/",
    ];

    for (const value of unsafe) {
      assert.throws(
        () =>
          loadApplicationProxyConfig({
            registrationsJson: registrations([{ app_id: "example-app", ui_upstream: value }]),
            enabled: true,
          }),
        /ui_upstream for "example-app"/,
        `ui_upstream accepted ${value}`,
      );
      assert.throws(
        () =>
          loadApplicationProxyConfig({
            registrationsJson: registrations([
              { app_id: "example-app", ui_upstream: "http://ui.invalid", service_upstream: value },
            ]),
            enabled: true,
          }),
        /service_upstream for "example-app"/,
        `service_upstream accepted ${value}`,
      );
    }
  });

  test("rejects malformed registration lists", () => {
    const invalid = [
      ["{}", /must be an array/],
      ['[{"app_id":"example-app"}]', /ui_upstream for "example-app"/],
      ['[{"app_id":"Example","ui_upstream":"http://ui.invalid"}]', /without a valid app_id/],
      ['[{"app_id":"example-app\\n","ui_upstream":"http://ui.invalid"}]', /without a valid app_id/],
      // An id spelled like an nginx map-block directive is emitted into
      // production nginx config as syntax rather than as a map key.
      ...["default", "hostnames", "include", "volatile"].map((reserved) => [
        `[{"app_id":"${reserved}","ui_upstream":"http://ui.invalid"}]`,
        /without a valid app_id/,
      ]),
      ['[{"app_id":"example-app","ui_upstream":"http://ui.invalid","module_key":"example"}]', /unsupported keys/],
      [
        '[{"app_id":"example-app","ui_upstream":"http://ui.invalid","service_required":"true"}]',
        /service_required for "example-app" must be a boolean/,
      ],
      [
        '[{"app_id":"a","ui_upstream":"http://ui.invalid"},{"app_id":"a","ui_upstream":"http://ui.invalid"}]',
        /duplicate app_id "a"/,
      ],
      ["[", /is not valid JSON/],
    ];

    for (const [registrationsJson, expected] of invalid) {
      assert.throws(() => parseApplicationRegistrations(registrationsJson), expected, registrationsJson);
    }
    assert.deepEqual(parseApplicationRegistrations(undefined), []);
  });

  test("routes overlapping application ids to their own upstream in either registration order", () => {
    const acme = {
      app_id: "acme",
      ui_upstream: "http://acme-ui.invalid",
      service_upstream: "http://acme-api.invalid",
    };
    const forecast = {
      app_id: "acme-forecast",
      ui_upstream: "http://forecast-ui.invalid",
      service_upstream: "http://forecast-api.invalid",
    };

    for (const entries of [
      [acme, forecast],
      [forecast, acme],
    ]) {
      const config = loadApplicationProxyConfig({ registrationsJson: registrations(entries), enabled: true });
      const order = entries.map((entry) => entry.app_id).join(",");

      for (const [requestUrl, target, rewritten] of [
        ["/apps/acme/main.js", "http://acme-ui.invalid", "/apps/acme/main.js"],
        ["/apps/acme", "http://acme-ui.invalid", "/apps/acme"],
        ["/apps/acme?debug=1", "http://acme-ui.invalid", "/apps/acme?debug=1"],
        ["/apps/acme-forecast/main.js", "http://forecast-ui.invalid", "/apps/acme-forecast/main.js"],
        ["/apps/acme-forecast", "http://forecast-ui.invalid", "/apps/acme-forecast"],
        ["/apps/acme-forecast?debug=1", "http://forecast-ui.invalid", "/apps/acme-forecast?debug=1"],
        ["/app-services/acme/items", "http://acme-api.invalid", "/items"],
        ["/app-services/acme-forecast/items?view=full", "http://forecast-api.invalid", "/items?view=full"],
      ]) {
        const entry = resolveThroughViteProxy(config.proxy, requestUrl);
        assert.ok(entry, `${order}: no proxy entry for ${requestUrl}`);
        assert.equal(entry.target, target, `${order}: ${requestUrl}`);
        assert.equal(entry.rewrite(requestUrl), rewritten, `${order}: ${requestUrl}`);
        assert.equal(config.classifyRequest(requestUrl), "proxy", `${order}: ${requestUrl}`);
      }

      // An unregistered lookalike must reach no upstream at all.
      assert.equal(resolveThroughViteProxy(config.proxy, "/apps/acme-other/main.js"), null, order);
      assert.equal(config.classifyRequest("/apps/acme-other/main.js"), 404, order);
    }
  });
});

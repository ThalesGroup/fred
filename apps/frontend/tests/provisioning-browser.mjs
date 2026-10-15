// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

// Full Fred UI + real OIDC login, manager, PostgreSQL and OpenFGA. Only the
// unrelated control-plane shell reads below are fixtures; no manager response,
// Keycloak token, generated slice or provisioning action is mocked.
import assert from "node:assert/strict";
import { cp, mkdir, readFile, writeFile } from "node:fs/promises";
import { execFileSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { chromium, expect as baseExpect } from "@playwright/test";
import JSZip from "jszip";

const manager = process.env.FRED_MANAGER_BROWSER_URL;
const realm = process.env.FRED_MANAGER_BROWSER_REALM;
const bundle = process.env.FRED_MANAGER_BROWSER_BUNDLE;
const port = Number(process.env.FRED_MANAGER_BROWSER_PORT);
assert(manager && realm && bundle && port, "Run make test-provisioning-browser to create isolated services");
for (const url of [manager, realm]) assert.equal(new URL(url).hostname, "127.0.0.1");
process.env.VITE_BACKEND_URL_FRED_MANAGER = manager;
const { createServer } = await import("vite");
const server = await createServer({ server: { host: "127.0.0.1", port, strictPort: true }, logLevel: "error" });
let browser;
const unexpected = [];
const pageErrors = [];
const origin = `http://127.0.0.1:${port}`;
const expect = baseExpect.configure({ timeout: 60_000 });

async function login(username, password, path = "/admin/provisioning") {
  const context = await browser.newContext({ locale: "en", viewport: { width: 1280, height: 900 } });
  // Neutral admitted shell with no control-plane administrative authority.
  // Listing these endpoints explicitly makes unexpected dependencies fail the test.
  await context.route("**/control-plane/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let value;
    switch (path) {
      case "/control-plane/v1/frontend/config":
        value = {
          user_auth: { enabled: true, realm_url: realm, client_id: "app", provider: "keycloak" },
          gcu_version: null,
          root_bootstrap_required: false,
          platform_access_enabled: false,
        };
        break;
      case "/control-plane/v1/frontend/bootstrap":
        value = {
          current_user: {
            id: username,
            username,
            first_name: username,
            last_name: "",
            email: `${username}@example.com`,
          },
          active_team: { id: "shell-personal", name: "Personal", permissions: [], my_relations: [] },
          available_teams: [],
          feature_flags: {},
          permissions: { platform_roles: [] },
          team_admin_charter_enabled: false,
        };
        break;
      case "/control-plane/v1/announcements/active":
        value = [];
        break;
      case "/control-plane/v1/announcements/patch-notes":
        value = { patch_notes: [], pending_announcement_id: null };
        break;
      case "/control-plane/v1/tasks":
        value = { tasks: [] };
        break;
      default:
        unexpected.push(path);
        await route.abort();
        return;
    }
    await route.fulfill({ json: value });
  });
  await context.route("**/knowledge-flow/v1/tasks?*", (route) => route.fulfill({ json: { tasks: [] } }));
  const page = await context.newPage();
  page.on("pageerror", (error) => pageErrors.push(error.message));
  let bearer;
  page.on("request", (request) => {
    if (request.url() === `${origin}/fred-manager/v1/me`) bearer = request.headers().authorization;
  });
  await page.goto(origin + path);
  await page.locator("#username").fill(username);
  await page.locator("#password").fill(password);
  await page.locator("#kc-login").click();
  await expect(page.getByRole("heading", { name: "Provisioning", exact: true })).toBeVisible();
  await expect.poll(() => bearer).toMatch(/^Bearer /);
  return { context, page, bearer };
}

async function importFile(page, file, expectedStatus = 200) {
  await page.locator('input[type="file"]').setInputFiles(file);
  const response = page.waitForResponse((r) => r.url() === `${origin}/fred-manager/v1/import-export/import`);
  await page.getByRole("button", { name: "Import the bundle", exact: true }).click();
  const result = await response;
  assert.equal(result.status(), expectedStatus);
  const body = await result.json();
  if (expectedStatus === 200) {
    await expect(page.getByRole("heading", { name: "Import completed" })).toBeVisible();
    const counts = await page.locator("dl dd").allTextContents();
    assert.deepEqual(counts.map(Number), [
      body.identities_resolved,
      body.identities_created,
      body.spaces_reconciled,
      body.grants_acknowledged,
    ]);
  } else {
    await expect(page.getByRole("alert")).toContainText("The import did not complete successfully.");
    await expect(page.getByRole("heading", { name: "Import completed" })).toHaveCount(0);
  }
  return body;
}

async function get(context, bearer, path) {
  const response = await context.request.get(`${origin}/fred-manager/v1${path}`, {
    headers: { Authorization: bearer },
  });
  assert.equal(response.status(), 200);
  return response.json();
}

try {
  await server.listen();
  browser = await chromium.launch({ headless: true });
  const root = await login("root", "it-root", "/admin");
  await expect(root.page.getByRole("link", { name: "Provisioning", exact: true })).toBeVisible();
  await expect(root.page.getByRole("link", { name: "Migration", exact: true })).toHaveCount(0);

  // Hold the actual outgoing request, assert pending controls, then allow it to
  // reach the real importer. No fabricated result can satisfy this assertion.
  let release;
  const held = new Promise((resolve) => {
    release = resolve;
  });
  let reached;
  const entering = new Promise((resolve) => {
    reached = resolve;
  });
  await root.page.route(
    "**/fred-manager/v1/import-export/import",
    async (route) => {
      reached();
      await held;
      await route.continue();
    },
    { times: 1 },
  );
  const firstPromise = importFile(root.page, bundle);
  await entering;
  await expect(root.page.getByRole("button", { name: "Importing...", exact: true })).toBeDisabled();
  await expect(root.page.locator('input[type="file"]')).toBeDisabled();
  await expect(root.page.getByRole("heading", { name: "Import completed" })).toHaveCount(0);
  release();
  const first = await firstPromise;
  assert.equal(first.identities_resolved, 15);
  assert.equal(first.identities_created, 15);
  assert.equal(first.spaces_reconciled, 4);
  const teamsBefore = await get(root.context, root.bearer, "/admin/teams");
  const grantsBefore = await get(root.context, root.bearer, "/users/platform-roles");
  const replay = await importFile(root.page, bundle);
  assert.equal(replay.identities_created, 0);
  assert.equal(replay.grants_acknowledged, first.grants_acknowledged);
  assert.deepEqual(await get(root.context, root.bearer, "/admin/teams"), teamsBefore);
  assert.deepEqual(await get(root.context, root.bearer, "/users/platform-roles"), grantsBefore);

  // The same public builder produces a variant containing a project.
  const fixture = resolve(dirname(bundle), "project-fixture");
  await cp("../fred-manager/tests/fixtures/import_export/demo_provisioning", fixture, { recursive: true });
  await writeFile(
    `${fixture}/projects.json`,
    JSON.stringify([
      { ref: "browser-project", name: "Browser project", team: "northbridge", roles: { bob: ["admin", "member"] } },
    ]),
  );
  const projectZip = resolve(dirname(bundle), "project.zip");
  execFileSync("make", ["-C", "../fred-manager", "build-demo-bundle"], {
    env: { ...process.env, DEMO_PROVISIONING_FIXTURE_DIR: fixture, DEMO_BUNDLE_FILE: projectZip },
    stdio: "pipe",
  });
  const projectResult = await importFile(root.page, projectZip);
  assert.equal(projectResult.spaces_reconciled, 5);
  assert.equal(projectResult.identities_created, 0);

  await mkdir("target", { recursive: true });
  await root.page.screenshot({ path: "target/provisioning-browser.png", fullPage: true });
  await root.page.setViewportSize({ width: 760, height: 900 });
  assert(await root.page.locator("main").evaluate((node) => node.scrollWidth <= node.clientWidth));
  await root.page.screenshot({ path: "target/provisioning-browser-narrow.png", fullPage: true });

  const legacy = new JSZip().file("manifest.json", JSON.stringify({ format_version: 1 })).file("users.json", "[]");
  const failure = await importFile(
    root.page,
    { name: "legacy.zip", mimeType: "application/zip", buffer: await legacy.generateAsync({ type: "nodebuffer" }) },
    422,
  );
  assert.equal(failure.detail, "not_yet_supported");
  await expect(root.page.getByRole("alert")).toContainText("This bundle format is not yet supported.");
  await expect(root.page.getByRole("alert")).toContainText("Some changes may already be applied.");

  const bob = await login("bob", "Azerty123_");
  await expect(bob.page.getByRole("alert")).toContainText("Provisioning requires a platform administrator role");
  await expect(bob.page.locator('input[type="file"]')).toHaveCount(0);
  await expect(bob.page.getByRole("link", { name: "Provisioning", exact: true })).toHaveCount(0);
  const spaces = await get(bob.context, bob.bearer, "/me/spaces");
  const project = spaces.find((space) => space.name === "Browser project");
  const north = spaces.find((space) => space.name === "northbridge");
  const organization = spaces.find((space) => space.name === "Demo");
  assert.deepEqual(project.path, [organization.id, north.id, project.id]);
  assert.deepEqual([...project.roles].sort(), ["admin", "member"]);
  assert.deepEqual(north.roles, ["editor"]);
  const denied = await bob.context.request.post(`${origin}/fred-manager/v1/import-export/import`, {
    headers: { Authorization: bob.bearer },
    multipart: { file: { name: "demo.zip", mimeType: "application/zip", buffer: await readFile(bundle) } },
  });
  assert.equal(denied.status(), 403);

  const alice = await login("alice", "Azerty123_");
  // An ordinary platform admin reaches the page, but this bundle declares an
  // admin grant: only the bootstrap root may apply it, including on replay.
  await expect(alice.page.locator('input[type="file"]')).toHaveCount(1);
  await importFile(alice.page, bundle, 403);
  assert.deepEqual(await get(root.context, root.bearer, "/admin/teams"), teamsBefore);
  assert.deepEqual(await get(bob.context, bob.bearer, "/me/spaces"), spaces);
  assert.deepEqual(unexpected, [], "Unexpected control-plane dependency");
  assert.deepEqual(pageErrors, [], "Browser application errors");
  console.log(
    "Provisioning browser acceptance passed: OIDC login, navigation, multipart import, pending state, reports, replay, project hierarchy/roles, legacy rejection and access refusals.",
  );
} finally {
  await browser?.close();
  await server.close();
}

// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

// Real first-user journey; any control-plane or knowledge-flow dependency fails.
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
  await context.route(/\/(control-plane|knowledge-flow|fred-agents|agentic-backend|runtime)\/v1\//, async (route) => {
    unexpected.push(new URL(route.request().url()).pathname);
    await route.abort();
  });
  if (username === "root")
    await context.route("**/fred-manager/v1/frontend/config", (route) => route.abort(), { times: 1 });
  const page = await context.newPage();
  page.on("pageerror", (error) => pageErrors.push(error.message));
  let bearer;
  page.on("request", (request) => {
    if (request.url() === `${origin}/fred-manager/v1/me/onboarding`) bearer = request.headers().authorization;
  });
  await page.goto(origin + path);
  if (username === "root") {
    await expect(page.getByRole("alert")).toContainText("Unable to load your access");
    await page.getByRole("button", { name: "Reload", exact: true }).click();
  }
  await page.locator("#username").fill(username);
  await page.locator("#password").fill(password);
  await page.locator("#kc-login").click();
  await expect.poll(() => bearer).toMatch(/^Bearer /);
  const before = await get(context, bearer, "/me/onboarding");
  assert.equal(before.acceptance, null, "Import must not accept terms for anyone");
  const denied = await context.request.get(`${origin}/fred-manager/v1/me/spaces`, {
    headers: { Authorization: bearer },
  });
  assert.equal(denied.status(), 403);
  if (username === "root") {
    // Logout before consent must not imply acceptance when the person returns.
    await logout(page);
    await page.locator("#username").fill(username);
    await page.locator("#password").fill(password);
    await page.locator("#kc-login").click();
  }
  await acceptTerms(page);
  if (username === "root") {
    await logout(page);
    await page.locator("#username").fill(username);
    await page.locator("#password").fill(password);
    await page.locator("#kc-login").click();

    const secret = page.getByLabel("Bootstrap secret", { exact: false });
    await secret.fill("wrong-but-long-enough");
    await page.getByRole("button", { name: "Become platform administrator", exact: true }).click();
    await expect(page.getByText("This bootstrap secret is not valid. Please try again.")).toBeVisible();
    await expect(secret).toHaveValue("");
    await secret.fill(process.env.FRED_MANAGER_TEST_BOOTSTRAP_TOKEN);
    await page.getByRole("button", { name: "Become platform administrator", exact: true }).click();
    await expect(page.getByText("You are now the platform administrator, root.")).toBeVisible();
    await page.getByRole("button", { name: "Continue", exact: true }).click();
    await page.getByRole("button", { name: "Home", exact: true }).click();
    await expect(page.getByText("You do not belong to any organization or space.")).toBeVisible();
    assert.deepEqual(await get(context, bearer, "/me/spaces"), []);
    await page.getByRole("button", { name: "Technical console", exact: true }).click();
    await page.getByRole("link", { name: "Provisioning", exact: true }).click();
  }
  await expect(page.getByRole("heading", { name: "Provisioning", exact: true })).toBeVisible();
  return { context, page, bearer };
}

async function logout(page) {
  const trigger = page.getByRole("button", { name: /'s account$/ });
  await trigger.focus();
  await page.keyboard.press("Enter");
  const disconnect = page.getByRole("menuitem", { name: "Disconnect", exact: true });
  await expect(disconnect).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(trigger).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(disconnect).toBeFocused();
  await page.keyboard.press("Enter");
}

async function assertBoundedNavigation(page) {
  await expect(page.getByRole("navigation", { name: "Main navigation", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Marketplace", exact: true })).toHaveCount(0);
  for (const path of ["/team/unknown/resources", "/team/unknown/agents", "/admin/teams", "/marketplace/teams"]) {
    await page.goto(origin + path);
    await expect(page).toHaveURL(origin + "/home");
    await expect(page.getByRole("heading", { name: "Your spaces", exact: true })).toBeVisible();
  }
}

async function acceptTerms(page) {
  const accept = page.getByRole("button", { name: "Accept the TOS", exact: true });
  await expect(accept).toBeVisible();
  await page.locator('[class*="gcuEnd"]').scrollIntoViewIfNeeded();
  await expect(accept).toBeEnabled();
  await accept.click();
  await expect(accept).toHaveCount(0);
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
  await assertBoundedNavigation(root.page);
  await root.page.getByRole("button", { name: "Technical console", exact: true }).click();
  await expect(root.page.getByRole("heading", { name: "Provisioning", exact: true })).toBeVisible();

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
  await root.page.setViewportSize({ width: 390, height: 844 });
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

  assert.deepEqual(await get(root.context, root.bearer, "/me/spaces"), []);
  // Switch identities in the same browser, exercising logout and fresh Redux state.
  let bobBearer;
  root.page.on("request", (request) => {
    if (request.url() === `${origin}/fred-manager/v1/me`) bobBearer = request.headers().authorization;
  });
  await logout(root.page);
  await root.page.locator("#username").fill("bob");
  await root.page.locator("#password").fill("Azerty123_");
  await root.page.locator("#kc-login").click();
  // Leave Bob's consent pending, return to root, then check Bob still needs his own consent.
  await expect(root.page.getByRole("button", { name: "Accept the TOS", exact: true })).toBeVisible();
  await logout(root.page);
  await root.page.locator("#username").fill("root");
  await root.page.locator("#password").fill("it-root");
  await root.page.locator("#kc-login").click();
  await root.page.getByRole("button", { name: "Home", exact: true }).click();
  await expect(root.page.getByText("You do not belong to any organization or space.")).toBeVisible();
  await expect(root.page.getByRole("heading", { name: "Browser project", exact: true })).toHaveCount(0);
  await logout(root.page);
  await root.page.locator("#username").fill("bob");
  await root.page.locator("#password").fill("Azerty123_");
  await root.page.locator("#kc-login").click();
  await acceptTerms(root.page);
  await root.page.getByRole("button", { name: "Home", exact: true }).click();
  await expect(root.page.getByRole("heading", { name: "Your spaces", exact: true })).toBeVisible();
  await expect(root.page.getByRole("heading", { name: "Demo", exact: true })).toBeVisible();
  await expect(root.page.getByRole("heading", { name: "Browser project", exact: true })).toHaveCount(0);
  assert.equal(new URL(root.page.url()).pathname, "/home");
  assert.equal(new URL(root.page.url()).search, "");
  await expect(root.page.getByRole("link", { name: "Demo", exact: true })).toHaveAttribute("href", "/home");
  await expect(root.page.getByText("You do not belong to any organization or space.")).toHaveCount(0);
  await root.page.getByRole("link", { name: "Browser project", exact: true }).click();
  await expect(root.page.getByRole("region", { name: "Browser project", exact: true })).toContainText(
    "Demo / northbridge / Browser project",
  );
  await expect(root.page.getByRole("heading", { name: "northbridge", exact: true })).toHaveCount(0);
  await root.page.screenshot({ path: "target/provisioning-spaces-narrow.png", fullPage: true });
  await root.page.setViewportSize({ width: 1280, height: 900 });
  await root.page.screenshot({ path: "target/provisioning-spaces.png", fullPage: true });
  const bob = { page: root.page, context: root.context, bearer: bobBearer };
  await assertBoundedNavigation(bob.page);
  await expect(bob.page.getByRole("button", { name: "Technical console", exact: true })).toHaveCount(0);
  await bob.page.goto(origin + "/admin/provisioning");
  await expect(bob.page.getByRole("alert")).toContainText("Provisioning requires a platform administrator role");
  await expect(bob.page.locator('input[type="file"]')).toHaveCount(0);
  await expect(bob.page.getByRole("link", { name: "Provisioning", exact: true })).toHaveCount(0);
  const spaces = await get(bob.context, bob.bearer, "/me/spaces");
  const project = spaces.find((space) => space.name === "Browser project");
  const north = spaces.find((space) => space.name === "northbridge");
  const organization = spaces.find((space) => space.name === "Demo");
  assert.deepEqual(project.path, [organization.id, north.id, project.id]);
  assert.deepEqual([...project.roles].sort(), ["admin", "editor", "member"]);
  assert.deepEqual(project.inherited_roles, ["editor"]);
  assert.deepEqual(north.roles, ["editor"]);
  const denied = await bob.context.request.post(`${origin}/fred-manager/v1/import-export/import`, {
    headers: { Authorization: bob.bearer },
    multipart: { file: { name: "demo.zip", mimeType: "application/zip", buffer: await readFile(bundle) } },
  });
  assert.equal(denied.status(), 403);

  const alice = await login("alice", "Azerty123_");
  // Another platform owner reaches the page and replays the bundle without changes.
  await expect(alice.page.locator('input[type="file"]')).toHaveCount(1);
  await importFile(alice.page, bundle, 200);
  assert.deepEqual(await get(root.context, root.bearer, "/admin/teams"), teamsBefore);
  assert.deepEqual(await get(bob.context, bob.bearer, "/me/spaces"), spaces);
  assert.deepEqual(unexpected, [], "Unexpected control-plane dependency");
  assert.deepEqual(pageErrors, [], "Browser application errors");
  console.log(
    "Provisioning browser acceptance passed: OIDC login, personal terms, root bootstrap, logout/account switch, empty root memberships, navigation, multipart import, pending state, reports, replay, project hierarchy/roles, legacy rejection and access refusals.",
  );
} catch (error) {
  console.error({ pageErrors, unexpected });
  throw error;
} finally {
  await browser?.close();
  await server.close();
}

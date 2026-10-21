// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

// Real manager journey with unavailable non-migrated services and the complete Fred UI.
import assert from "node:assert/strict";
import { cp, mkdir, readFile, writeFile } from "node:fs/promises";
import { execFileSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { chromium, expect as baseExpect } from "@playwright/test";
import JSZip from "jszip";
import { documentStorageJourney } from "./document-storage-browser.mjs";
import { assertAccountAtBottom } from "./assert-app-layout.mjs";

const manager = process.env.CONTROL_PLANE_BROWSER_URL;
const realm = process.env.CONTROL_PLANE_BROWSER_REALM;
const bundle = process.env.CONTROL_PLANE_BROWSER_BUNDLE;
const port = Number(process.env.CONTROL_PLANE_BROWSER_PORT);
assert(manager && realm && bundle && port, "Run make test-provisioning-browser to create isolated services");
for (const url of [manager, realm]) assert.equal(new URL(url).hostname, "127.0.0.1");
process.env.VITE_BACKEND_URL_CONTROL_PLANE = manager;
const { createServer } = await import("vite");
const server = await createServer({
  cacheDir: `node_modules/.vite-browser-${port}`,
  server: { host: "127.0.0.1", port, strictPort: true },
  logLevel: "error",
});
let browser;
const unavailableServices = [];
const pageErrors = [];
const assetFailures = [];
const origin = `http://127.0.0.1:${port}`;
const expect = baseExpect.configure({ timeout: 60_000 });

async function login(username, password, path = "/admin/provisioning") {
  const context = await browser.newContext({ locale: "en", viewport: { width: 1280, height: 900 } });
  await context.route(/\/(control-plane|knowledge-flow|fred-agents|agentic-backend|runtime)\/v1\//, async (route) => {
    unavailableServices.push(new URL(route.request().url()).pathname);
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Service unavailable in manager fixture" }),
    });
  });
  if (username === "root")
    await context.route("**/control-plane/v1/frontend/config", (route) => route.abort(), { times: 1 });
  const page = await context.newPage();
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("requestfailed", (request) => {
    if (request.resourceType() === "script")
      assetFailures.push({ path: new URL(request.url()).pathname, error: request.failure()?.errorText });
  });
  let bearer;
  page.on("request", (request) => {
    if (request.url() === `${origin}/control-plane/v1/me/onboarding`) bearer = request.headers().authorization;
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
  const denied = await context.request.get(`${origin}/control-plane/v1/me/spaces`, {
    headers: { Authorization: bearer },
  });
  assert.equal(denied.status(), 403);
  if (username === "root") {
    // Every direct account URL still passes personal admission first.
    for (const accountPath of ["/settings", "/gcu", "/gdpr", "/release-notes"]) {
      await page.goto(origin + accountPath);
      await expect(page.getByRole("button", { name: "Accept the TOS", exact: true })).toBeVisible();
      await page.getByRole("button", { name: /'s account$/ }).click();
      await expect(page.getByRole("menuitem", { name: "Profile", exact: true })).toHaveCount(0);
      await page.keyboard.press("Escape");
    }
    await page.goto(origin + path);
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

    await page.goto(origin + "/settings");
    await expect(page.getByLabel("Bootstrap secret", { exact: false })).toBeVisible();
    await page.goto(origin + path);
    const secret = page.getByLabel("Bootstrap secret", { exact: false });
    await secret.fill("wrong-but-long-enough");
    await page.getByRole("button", { name: "Become platform administrator", exact: true }).click();
    await expect(page.getByText("This bootstrap secret is not valid. Please try again.")).toBeVisible();
    await expect(secret).toHaveValue("");
    await secret.fill(process.env.CONTROL_PLANE_TEST_BOOTSTRAP_TOKEN);
    await page.getByRole("button", { name: "Become platform administrator", exact: true }).click();
    await expect(page.getByText("You are now the platform administrator, root.")).toBeVisible();
    await page.getByRole("button", { name: "Continue", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Organizations", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Home", exact: true })).toHaveCount(0);
    assert.deepEqual(await get(context, bearer, "/me/spaces"), []);
    await page.getByRole("button", { name: "Technical console", exact: true }).click();
    await page.getByRole("link", { name: "Provisioning", exact: true }).click();
  }
  await expect(page.getByRole("heading", { name: path === "/home" ? /^Hello / : "Provisioning" })).toBeVisible();
  return { context, page, bearer };
}

async function logout(page) {
  const trigger = page.getByRole("button", { name: /'s account$/ });
  await trigger.focus();
  await page.keyboard.press("Enter");
  const disconnect = page.getByRole("menuitem", { name: "Disconnect", exact: true });
  await expect(page.getByRole("menuitem").first()).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(trigger).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("menuitem").first()).toBeFocused();
  for (let item = 1; item < (await page.getByRole("menuitem").count()); item++) await page.keyboard.press("Tab");
  await expect(disconnect).toBeFocused();
  await page.keyboard.press("Enter");
}

async function assertPreservedNavigation(page) {
  await expect(page.getByRole("navigation", { name: "Main navigation", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Marketplace", exact: true })).toBeVisible();
  for (const path of [
    "/team/unknown/resources",
    "/team/unknown/agents",
    "/team/unknown/prompts",
    "/marketplace/teams",
  ]) {
    await page.goto(origin + path);
    await expect(page).toHaveURL(origin + path);
  }
  await page.goto(origin + "/home");
}

async function acceptTerms(page) {
  const accept = page.getByRole("button", { name: "Accept the TOS", exact: true });
  await expect(accept).toBeVisible();
  await page.locator('[class*="gcuEnd"]').scrollIntoViewIfNeeded();
  await expect(accept).toBeEnabled();
  await accept.click();
  await expect(accept).toHaveCount(0);
}

// Uses the real shared screens and preferences, preserving governance state.
async function assertAccountPages({ page, context, bearer }, owner) {
  const consentBefore = await get(context, bearer, "/me/onboarding");
  const spacesBefore = await get(context, bearer, "/me/spaces");
  let consentWrites = 0;
  const trackConsent = (request) => {
    if (request.url() === `${origin}/control-plane/v1/gcu` && request.method() === "POST") consentWrites++;
  };
  page.on("request", trackConsent);
  const viewport = page.viewportSize();
  await page.setViewportSize({ width: 1280, height: 900 });
  await assertAccountAtBottom(page);
  const trigger = page.getByRole("button", { name: /'s account$/ });
  await trigger.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("menuitem", { name: "Profile", exact: true })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(origin + "/settings");
  await expect(page.getByText("Your profile", { exact: true })).toBeVisible();
  await expect(page.getByText(owner ? "Root Admin" : "Bob Rigg", { exact: true })).toBeVisible();
  await expect(page.getByText(owner ? "root@example.com" : "bob@app.com", { exact: true })).toBeVisible();
  if (!owner) await expect(page.getByText("root@example.com", { exact: true })).toHaveCount(0);
  const roles = page.getByText(/^Platform roles:/);
  await expect(roles).toContainText(owner ? "platform_owner" : "None");
  if (!owner) {
    await expect(page.getByText(/platform_owner/)).toHaveCount(0);
    await expect(page.getByText("Organization: Demo", { exact: true })).toBeVisible();
  }
  await expect(page.getByText("Profile picture", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "UI theme", exact: true }).click();
  await page.getByRole("option", { name: "Cloud", exact: true }).click();
  await page.reload();
  await expect(page.getByRole("button", { name: "UI theme", exact: true })).toContainText("Cloud");
  await expect(page.locator("html")).toHaveAttribute("data-ui-theme", "cloud");
  await page.getByRole("radio", { name: "Dark", exact: true }).click();
  await page.reload();
  await expect(page.getByRole("radio", { name: "Dark", exact: true })).toBeChecked();
  await page.getByRole("radio", { name: "French", exact: true }).click();
  await page.reload();
  await expect(page.getByText("Votre profil", { exact: true })).toBeVisible();
  await page.getByRole("radio", { name: "Anglais", exact: true }).click();
  await expect(page.getByText("Your profile", { exact: true })).toBeVisible();
  await mkdir("target", { recursive: true });
  await page.screenshot({ path: `target/account-${owner ? "owner" : "member"}.png`, fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  assert(await page.locator("body").evaluate((node) => node.scrollWidth <= node.clientWidth));
  await page.screenshot({ path: `target/account-${owner ? "owner" : "member"}-narrow.png`, fullPage: true });
  await page.getByRole("radio", { name: "Light", exact: true }).click();
  await page.reload();
  await expect(page.getByRole("radio", { name: "Light", exact: true })).toBeChecked();
  await page.screenshot({ path: `target/account-${owner ? "owner" : "member"}-light.png`, fullPage: true });

  for (const path of ["/gcu", "/gdpr", "/release-notes"]) {
    await page.goto(origin + "/settings");
    await page.locator(`a[href="${path}"]`).click();
    await expect(page).toHaveURL(origin + path);
    await page.reload(); // Direct URLs retain the same admitted page.
    await expect(page).toHaveURL(origin + path);
    await expect(page.getByRole("button", { name: "Accept the TOS", exact: true })).toHaveCount(0);
    if (path === "/release-notes") {
      await expect(page.getByRole("button", { name: "Copy", exact: true })).toBeVisible();
    } else {
      await expect(page.locator('[class*="gcuContent"], [class*="gdprContent"]')).toContainText(/\S/);
      if (path === "/gdpr") await expect(page.getByText("Privacy information", { exact: true })).toBeVisible();
    }
    assert(await page.locator("body").evaluate((node) => node.scrollWidth <= node.clientWidth));
    await page.screenshot({
      path: `target/account-${owner ? "owner" : "member"}-${path.slice(1)}-narrow.png`,
      fullPage: true,
    });
    await page.getByRole("button", { name: path === "/release-notes" ? "Back" : "Back to app", exact: true }).click();
    await expect(page).toHaveURL(origin + (owner ? "/admin/organizations" : "/home"));
  }
  const missingNotes = /\/release\.md$/;
  await page.route(missingNotes, (route) => route.fulfill({ status: 404, body: "" }));
  await page.goto(origin + "/release-notes");
  await expect(page.getByText("No release notes available.", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Copy", exact: true })).toHaveCount(0);
  await page.unroute(missingNotes);
  await page.getByRole("button", { name: "Back", exact: true }).click();
  await expect(page).toHaveURL(origin + (owner ? "/admin/organizations" : "/home"));
  assert.deepEqual(await get(context, bearer, "/me/onboarding"), consentBefore);
  assert.deepEqual(await get(context, bearer, "/me/spaces"), spacesBefore);
  assert.equal(consentWrites, 0, "Consultation must not accept terms again");
  page.off("request", trackConsent);
  await page.setViewportSize(viewport);
}

async function importFile(page, file, expectedStatus = 200) {
  await page.locator('input[type="file"]').setInputFiles(file);
  const response = page.waitForResponse((r) => r.url() === `${origin}/control-plane/v1/import-export/import`);
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
  const response = await context.request.get(`${origin}/control-plane/v1${path}`, {
    headers: { Authorization: bearer },
  });
  assert.equal(response.status(), 200);
  return response.json();
}

try {
  await server.listen();
  await server.warmupRequest("/src/common/router.tsx");
  await server.waitForRequestsIdle();
  browser = await chromium.launch({ headless: true });
  const root = await login("root", "it-root", "/admin");
  if (process.env.CONTROL_PLANE_BROWSER_DOCUMENTS_ONLY === "1") {
    await importFile(root.page, bundle);
    const priya = await login("priya", "Azerty123_", "/home");
    const opening = priya.page.waitForResponse((r) => r.url().endsWith("/me/personal-space"));
    await priya.page.getByRole("button", { name: "Personal space", exact: true }).click();
    const opened = await opening;
    assert.equal(opened.status(), 201);
    const personal = await opened.json();
    await priya.page.goto(`${origin}/team/${personal.id}/resources`);
    await documentStorageJourney({ ...priya, origin, space: personal.id, expect });
    assert.deepEqual(pageErrors, [], "Browser application errors");
    console.log(
      "Manager document browser acceptance passed: original upload, lost acknowledgment, navigation, reload, conflict skip and identical download without processing services.",
    );
  } else {
    await expect(root.page.getByRole("link", { name: "Provisioning", exact: true })).toBeVisible();
    await expect(root.page.getByRole("link", { name: "Migration", exact: true })).toHaveCount(0);
    await assertAccountPages(root, true);
    await expect(root.page.getByRole("heading", { name: "Organizations", exact: true })).toBeVisible();
    await expect(root.page.getByRole("button", { name: "Home", exact: true })).toHaveCount(0);
    await root.page.goto(origin + "/marketplace");
    await expect(root.page).toHaveURL(origin + "/admin/organizations");
    await root.page.getByRole("link", { name: "Provisioning", exact: true }).click();
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
      "**/control-plane/v1/import-export/import",
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
    await cp("../control-plane/tests/fixtures/import_export/demo_provisioning", fixture, { recursive: true });
    await writeFile(
      `${fixture}/projects.json`,
      JSON.stringify([
        { ref: "browser-project", name: "Browser project", team: "northbridge", roles: { bob: ["admin", "member"] } },
      ]),
    );
    const projectZip = resolve(dirname(bundle), "project.zip");
    execFileSync("make", ["-C", "../control-plane", "build-demo-bundle"], {
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
      if (request.url() === `${origin}/control-plane/v1/me`) bobBearer = request.headers().authorization;
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
    await root.page.goto(origin + "/home");
    await expect(root.page.getByRole("heading", { name: "Organizations", exact: true })).toBeVisible();
    await expect(root.page.getByRole("heading", { name: "Browser project", exact: true })).toHaveCount(0);
    await logout(root.page);
    await root.page.locator("#username").fill("bob");
    await root.page.locator("#password").fill("Azerty123_");
    await root.page.locator("#kc-login").click();
    await acceptTerms(root.page);
    await root.page.getByRole("button", { name: "Home", exact: true }).click();
    await expect(root.page.getByRole("heading", { name: /^Hello / })).toBeVisible();
    await expect(root.page.getByRole("link", { name: "Demo", exact: true })).toHaveCount(0);
    const projectLink = root.page.getByRole("link", { name: "Browser project", exact: true });
    const projectHref = await projectLink.getAttribute("href");
    assert.match(projectHref, /^\/team\/[^/]+\/agents$/);
    await projectLink.click();
    await expect(root.page).toHaveURL(origin + projectHref);
    await expect(root.page.getByRole("link", { name: "Prompts", exact: true })).toBeVisible();
    await expect(root.page.getByRole("link", { name: "Resources", exact: true })).toBeVisible();
    await root.page.screenshot({ path: "target/provisioning-spaces-narrow.png", fullPage: true });
    await root.page.setViewportSize({ width: 1280, height: 900 });
    await root.page.screenshot({ path: "target/provisioning-spaces.png", fullPage: true });
    const bob = { page: root.page, context: root.context, bearer: bobBearer };
    await assertAccountPages(bob, false);
    await assertPreservedNavigation(bob.page);
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
    const denied = await bob.context.request.post(`${origin}/control-plane/v1/import-export/import`, {
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
    // Explicit eligibility: Bob has no entry and the real command denies creation.
    await bob.page.goto(origin + "/home");
    await expect(bob.page.getByRole("button", { name: "Personal space", exact: true })).toHaveCount(0);
    const bobOpen = await bob.context.request.post(`${origin}/control-plane/v1/me/personal-space`, {
      headers: { Authorization: bob.bearer },
      data: { organization_id: organization.id },
    });
    assert.equal(bobOpen.status(), 403);

    const priya = await login("priya", "Azerty123_", "/home");
    await assertAccountAtBottom(priya.page);
    const beforePersonal = await get(priya.context, priya.bearer, "/me/spaces");
    assert.equal(beforePersonal.filter((space) => space.personal_owner).length, 0);
    const personalEntry = priya.page.getByRole("button", { name: "Personal space", exact: true });
    let personalCalls = 0;
    let releasePersonal;
    let enteredPersonal;
    const personalHeld = new Promise((resolve) => {
      releasePersonal = resolve;
    });
    const personalEntering = new Promise((resolve) => {
      enteredPersonal = resolve;
    });
    await priya.page.route(
      "**/control-plane/v1/me/personal-space",
      async (route) => {
        personalCalls++;
        enteredPersonal();
        await personalHeld;
        await route.continue();
      },
      { times: 1 },
    );
    const firstPersonal = priya.page.waitForResponse((r) => r.url().endsWith("/me/personal-space"));
    await personalEntry.focus();
    await priya.page.keyboard.press("Enter");
    await personalEntering;
    await expect(personalEntry).toBeDisabled();
    await priya.page.keyboard.press("Enter");
    releasePersonal();
    const createdPersonal = await firstPersonal;
    assert.equal(createdPersonal.status(), 201);
    const personal = await createdPersonal.json();
    assert.equal(personalCalls, 1);
    await expect(priya.page).toHaveURL(origin + `/team/${personal.id}/agents`);
    await expect(priya.page.getByText("Personal space", { exact: true })).toBeVisible();
    const personalMembership = (await get(priya.context, priya.bearer, "/me/spaces")).find((s) => s.id === personal.id);
    assert.equal(personalMembership.organization_id, organization.id);
    assert.deepEqual(personalMembership.path, [personal.id]);
    await priya.page.getByRole("button", { name: "Home", exact: true }).click();
    await priya.page.getByRole("link", { name: "fredlab", exact: true }).click();
    await expect(priya.page.getByText("fredlab", { exact: true })).toBeVisible();
    await expect(priya.page.getByRole("link", { name: "Prompts", exact: true })).toBeVisible();
    await priya.page.getByRole("button", { name: "Home", exact: true }).click();
    const repeated = priya.page.waitForResponse((r) => r.url().endsWith("/me/personal-space"));
    await personalEntry.click();
    const reused = await repeated;
    assert.equal(reused.status(), 200);
    assert.equal((await reused.json()).id, personal.id);
    await expect(priya.page).toHaveURL(origin + `/team/${personal.id}/agents`);
    await priya.page.reload();
    await expect(priya.page.getByText("Personal space", { exact: true })).toBeVisible();
    await priya.page.screenshot({ path: "target/personal-space.png", fullPage: true });
    await priya.page.setViewportSize({ width: 390, height: 844 });
    await expect
      .poll(() => priya.page.locator("main").evaluate((node) => node.scrollWidth <= node.clientWidth))
      .toBe(true);
    await priya.page.screenshot({ path: "target/personal-space-narrow.png", fullPage: true });
    await priya.page.getByRole("button", { name: "Home", exact: true }).click();
    // A transport refusal stays visible and requires a fresh deliberate action.
    await priya.page.route(
      "**/control-plane/v1/me/personal-space",
      (route) =>
        route.fulfill({
          status: 401,
          contentType: "application/json",
          body: JSON.stringify({ detail: "expired" }),
        }),
      { times: 1 },
    );
    await personalEntry.click();
    await expect(priya.page.getByRole("alert")).toBeVisible();
    await expect(personalEntry).toBeEnabled();
    await personalEntry.click();
    await expect(priya.page.getByRole("alert")).toHaveCount(0);
    // Retained navigation reaches the original Resources screen. Folder lifecycle
    // and visual parity have separate focused acceptance.
    await priya.page.setViewportSize({ width: 1280, height: 900 });
    await priya.page.getByRole("link", { name: "Resources", exact: true }).click();
    await expect(priya.page).toHaveURL(origin + `/team/${personal.id}/resources`);
    await documentStorageJourney({ ...priya, origin, space: personal.id, expect });
    assert(!(await get(bob.context, bob.bearer, "/me/spaces")).some((item) => item.id === personal.id));
    assert.deepEqual(pageErrors, [], "Browser application errors");
    console.log(
      "Manager browser acceptance passed: admission, account pages, provisioning/replay, memberships, personal opening and retained product navigation with unavailable non-migrated services. Original upload, conflict skip, reload and identical download pass without processing services.",
    );
  }
} catch (error) {
  console.error({ pageErrors, assetFailures, unavailableServices });
  throw error;
} finally {
  await browser?.close();
  await server.close();
}

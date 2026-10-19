// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createHash } from "node:crypto";

export async function documentStorageJourney({ page, context, bearer, origin, space, expect }) {
  const processing = [];
  const calls = [];
  let uploads = 0;
  page.on("response", (r) => {
    if (r.url().includes("/fred-manager/v1/"))
      calls.push([r.request().method(), new URL(r.url()).pathname, r.status()]);
  });
  const observe = (request) => {
    const url = new URL(request.url());
    if (request.method() === "POST" && /^\/fred-manager\/v1\/folders\/[^/]+\/documents$/.test(url.pathname)) uploads++;
    // The unchanged application shell probes its global task feed on navigation.
    // Those unavailable status reads do not dispatch document processing.
    if (request.method() === "GET" && url.pathname.endsWith("/tasks")) return;
    if (/\/(knowledge-flow|runtime)\/v1\//.test(url.pathname)) processing.push(url.pathname);
  };
  page.on("request", observe);
  await page.getByRole("button", { name: "New folder", exact: true }).click();
  const folderDialog = page.getByRole("dialog", { name: "New folder" });
  await folderDialog.getByRole("textbox", { name: "Name" }).fill("Originals");
  const creating = page.waitForResponse((r) => r.request().method() === "POST" && r.url().endsWith("/folders"));
  await folderDialog.getByRole("button", { name: "Create", exact: true }).click();
  const created = await creating;
  assert.equal(created.status(), 201);
  const folder = await created.json();
  await page.getByRole("button", { name: "Originals", exact: true }).click();
  const bytes = Buffer.from("Stored without ingestion.\n".repeat(4096));
  const file = { name: "original.txt", mimeType: "text/plain", buffer: bytes };
  const select = async (files) => {
    await page.getByRole("button", { name: "Add files", exact: true }).click();
    const drawer = page.getByRole("dialog", { name: "Add documents" });
    await drawer.locator('input[type="file"]').setInputFiles(files);
    return drawer;
  };
  // The backend completes but the browser loses the acknowledgement. Navigation
  // must not cancel the controller, and receipt lookup must not send another file.
  let release;
  let entered;
  const hold = new Promise((resolve) => {
    release = resolve;
  });
  const entering = new Promise((resolve) => {
    entered = resolve;
  });
  let requestKey;
  let stored;
  // Drop the acknowledgement at the fetch boundary after a real browser request.
  // Keep multipart on the native browser transport, without replaying its body.
  await page.exposeBinding("loseUploadAcknowledgement", async (_, reply) => {
    assert.equal(reply.status, 201);
    requestKey = reply.key;
    stored = reply.receipt;
    entered();
    await hold;
  });
  await page.evaluate((pathname) => {
    const original = window.fetch;
    window.fetch = async (input, init) => {
      const request = input instanceof Request ? input : new Request(input, init);
      const response = await original(input, init);
      if (request.method === "POST" && new URL(request.url).pathname === pathname) {
        await window.loseUploadAcknowledgement({
          status: response.status,
          key: request.headers.get("Idempotency-Key"),
          receipt: await response.clone().json(),
        });
        window.fetch = original;
        throw new TypeError("Simulated lost upload acknowledgement");
      }
      return response;
    };
  }, `/fred-manager/v1/folders/${folder.id}/documents`);
  const drawer = await select([file]);
  await drawer.getByRole("button", { name: /^Import/ }).click();
  try {
    await Promise.race([
      entering,
      new Promise((_, reject) => setTimeout(() => reject(new Error("Original upload did not complete")), 45_000)),
    ]);
  } catch (error) {
    await page.screenshot({ path: "target/document-storage-failure.png", fullPage: true });
    console.error({ calls, visible: await page.locator("body").innerText() });
    throw error;
  }
  await page.getByRole("button", { name: "Home", exact: true }).click();
  const recovered = page.waitForResponse(
    (r) =>
      r.request().method() === "GET" && new URL(r.url()).pathname === `/fred-manager/v1/document-uploads/${requestKey}`,
  );
  release();
  const recovery = await recovered;
  assert.equal(recovery.status(), 200);
  const receipt = await recovery.json();
  assert.equal(receipt.status, "stored");
  assert.equal(receipt.document_id, stored.document_id);
  await page.goto(`${origin}/team/${space}/resources`);
  await page.getByRole("button", { name: "Originals", exact: true }).click();
  await expect(page.getByText("original.txt", { exact: true }).first()).toBeVisible();
  await page.reload();
  // Folder selection is page state, so re-enter it after a full navigation.
  await page.getByRole("button", { name: "Originals", exact: true }).click();
  // The existing DataTable renders CSS grid rows rather than native table rows.
  const documentRow = (name) =>
    page.locator('[class*="datatable-row"]').filter({ has: page.getByText(name, { exact: true }) });
  const row = documentRow("original.txt");
  await expect(row).toBeVisible();
  await expect(row).toContainText("Stored");
  await expect(row.getByRole("button", { name: "Preview", exact: true })).toBeDisabled();
  await row.getByRole("button", { name: "More actions", exact: true }).click();
  const downloading = page.waitForEvent("download");
  await page.getByRole("option", { name: "Download", exact: true }).click();
  const download = await downloading;
  assert.equal(download.suggestedFilename(), file.name);
  const saved = await readFile(await download.path());
  assert.deepEqual(saved, bytes);
  assert.equal(createHash("sha256").update(saved).digest("hex"), stored.sha256);
  assert.equal(uploads, 1);
  // One conflict decision preserves the original and permits the other file.
  const conflicts = await select([file, { ...file, name: "second.txt", buffer: Buffer.from("second") }]);
  await conflicts.getByRole("button", { name: /^Import/ }).click();
  await expect(conflicts.getByRole("button", { name: "Replace all", exact: true })).toBeDisabled();
  await conflicts.getByRole("button", { name: "Skip all", exact: true }).click();
  await conflicts.getByRole("button", { name: /^Import/ }).click();
  await expect(documentRow("second.txt")).toBeVisible();
  const response = await context.request.get(
    `${origin}/fred-manager/v1/spaces/${space}/entries?parent_id=${folder.id}`,
    { headers: { Authorization: bearer } },
  );
  assert.equal(response.status(), 200);
  const directory = await response.json();
  assert.equal(directory.total, 2);
  assert.equal(directory.items.find((entry) => entry.data.name === file.name).data.id, stored.document_id);
  await page.screenshot({ path: "target/document-storage.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: "target/document-storage-narrow.png", fullPage: true });
  assert.deepEqual(processing, [], "Document journey called a processing service");
  page.off("request", observe);
}

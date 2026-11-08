// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { appendFileSync, writeFileSync } from "node:fs";
import { mkdir } from "node:fs/promises";

// Runs only inside provisioning-browser's disposable SQL/Keycloak/Control Plane.
// All prompt and permission responses are real; no marketplace publication.
export async function promptsJourney({ login, root, origin, expect }) {
  const actors = {};
  const base = `${origin}/control-plane/v1`;
  const request = async (actor, method, path, expected = 200, data) => {
    const response = await actor.context.request.fetch(base + path, {
      method,
      headers: { Authorization: actor.bearer },
      ...(data === undefined ? {} : { data }),
    });
    assert.equal(
      response.status(),
      expected,
      `${method} ${path}${response.status() === expected ? "" : `: ${await response.text()}`}`,
    );
    return expected === 204 ? null : response.json();
  };
  const subject = (actor) => JSON.parse(Buffer.from(actor.bearer.split(".")[1], "base64url")).sub;
  const open = async (actor, space) => {
    await actor.page.goto(`${origin}/team/${space.id}/prompts`);
    await expect(
      actor.page.getByText(space.kind === "personal" ? "Your personal prompts" : "Space prompts", { exact: true }),
    ).toBeVisible();
  };
  const action = async (page, title, label) => {
    await page.getByRole("button", { name: `Actions for ${title}`, exact: true }).click();
    await page.getByRole("option", { name: label, exact: true }).click();
  };
  const exchange = async (page, method, path, click, status) => {
    const [response] = await Promise.all([
      page.waitForResponse(
        (r) => r.request().method() === method && new URL(r.url()).pathname === `/control-plane/v1${path}`,
      ),
      click(),
    ]);
    assert.equal(response.status(), status, `${method} ${path}`);
    return status === 204 ? null : response.json();
  };
  const created = [];
  await mkdir("target", { recursive: true });
  writeFileSync("target/prompts-browser-progress.log", "");
  const log = (message) => {
    console.log(message);
    appendFileSync("target/prompts-browser-progress.log", `${message}\n`);
  };
  try {
    const editor = (actors.boss = await login("boss", "Azerty123_", "/home"));
    const memberships = await request(editor, "GET", "/me/spaces");
    const collective = ["Acme", "Research", "Atlas"].map((name) => memberships.find((m) => m.name === name));
    const selectOrganization = async () => {
      await editor.page.getByRole("button", { name: "Organization", exact: true }).click();
      await editor.page.getByRole("option", { name: "Acme", exact: true }).click();
    };
    await selectOrganization();
    await editor.page.getByRole("link", { name: /Organization prompts/ }).click();
    await expect(editor.page).toHaveURL(`${origin}/team/${collective[0].id}/prompts`);
    await editor.page.goto(`${origin}/home`);
    await selectOrganization();
    const personal = await exchange(
      editor.page,
      "POST",
      "/me/personal-space",
      () => editor.page.getByRole("button", { name: "Personal space", exact: true }).click(),
      201,
    );
    assert.equal(
      (await request(editor, "GET", "/me/spaces")).find((s) => s.id === personal.id).organization_id,
      collective[0].id,
    );
    const spaces = [...collective, personal];
    assert.deepEqual(
      spaces.map((s) => s.kind),
      ["organization", "team", "project", "personal"],
    );
    for (const space of spaces) {
      const page = editor.page;
      const collection = `/spaces/${space.id}/prompts`;
      await open(editor, space);
      await page.getByRole("button", { name: "Manage categories", exact: true }).click();
      const categories = page.getByRole("dialog", { name: "Manage categories" });
      await categories.getByPlaceholder("New category...").fill("Acceptance");
      await categories.getByRole("button", { name: "Create", exact: true }).click();
      const category = await exchange(
        page,
        "POST",
        `/spaces/${space.id}/prompt-categories`,
        () => categories.getByRole("button", { name: "Save", exact: true }).click(),
        201,
      );
      await page.getByRole("button", { name: "Create prompt", exact: true }).first().click();
      const form = page.getByRole("dialog", { name: "New prompt", exact: true });
      await form.getByRole("textbox", { name: /^Name\b/ }).fill(`Acceptance ${space.kind}`);
      await form.getByRole("textbox", { name: /^Logical name/ }).fill("acceptance");
      await form.getByRole("textbox", { name: "Description", exact: true }).fill("Description retained");
      await form.getByRole("textbox", { name: /^Prompt text/ }).fill(`Original ${space.kind} text {{literal}}`);
      await form.getByRole("button", { name: "Acceptance", exact: true }).click();
      const prompt = await exchange(
        page,
        "POST",
        collection,
        () => form.getByRole("button", { name: "Create", exact: true }).click(),
        201,
      );
      assert.equal(prompt.space_id, space.id);
      assert.equal(prompt.category_id, category.id);
      const path = `${collection}/${prompt.prompt_id}`;
      await page.reload();
      await expect(page.getByText(prompt.display_name, { exact: true })).toBeVisible();
      await page.getByRole("button", { name: "Add to favorites", exact: true }).click();
      await expect(page.getByRole("button", { name: "Remove from favorites", exact: true })).toBeVisible();
      await page.reload();
      await expect(page.getByRole("button", { name: "Remove from favorites", exact: true })).toBeVisible();
      await page.getByText(prompt.display_name, { exact: true }).click();
      await expect(page.getByText(prompt.text, { exact: true })).toBeVisible();
      await page.getByRole("button", { name: "Close", exact: true }).click();
      await action(page, prompt.display_name, "Edit");
      const edit = page.getByRole("dialog", { name: "Edit prompt", exact: true });
      await expect(edit.getByRole("textbox", { name: /^Logical name/ })).toHaveAttribute("readonly", "");
      await edit.getByRole("textbox", { name: /^Name\b/ }).fill(`Renamed ${space.kind}`);
      // Another client edits a field omitted by the open form.
      await request(editor, "PATCH", path, 200, { text: `Concurrent ${space.kind} text` });
      const renamed = await exchange(
        page,
        "PATCH",
        path,
        () => edit.getByRole("button", { name: "Save", exact: true }).click(),
        200,
      );
      assert.equal(renamed.prompt_id, prompt.prompt_id);
      assert.equal(renamed.logical_name, "acceptance");
      assert.equal(renamed.text, `Concurrent ${space.kind} text`);
      assert.equal(renamed.description, prompt.description);
      await action(page, renamed.display_name, "Duplicate");
      const duplicate = page.getByRole("dialog", { name: "Duplicate this prompt", exact: true });
      await duplicate.getByRole("textbox", { name: /^Logical name/ }).fill("acceptance_copy");
      const copy = await exchange(
        page,
        "POST",
        collection,
        () => duplicate.getByRole("button", { name: "Duplicate", exact: true }).click(),
        201,
      );
      assert.notEqual(copy.prompt_id, prompt.prompt_id);
      assert.equal(copy.text, renamed.text);
      // Keep just one card for subsequent role checks.
      await request(editor, "DELETE", `${collection}/${copy.prompt_id}`, 204);
      await request(editor, "DELETE", `/spaces/${space.id}/prompt-categories/${category.id}`, 409);
      await page.reload();
      await expect(page.getByText(renamed.display_name, { exact: true })).toBeVisible();
      await page.screenshot({ path: `target/prompts-${space.kind}.png`, fullPage: true });
      created.push({ space, prompt: renamed, category, path, collection });
      log(`Prompt browser CRUD/favorite/category/concurrent-edit/duplicate: ${space.kind} passed`);
    }

    await editor.page.goto(`${origin}/home`);
    for (const item of created) {
      await editor.page.getByPlaceholder("Search agents, teams, prompts…").fill(item.prompt.display_name);
      await editor.page.getByRole("option").filter({ hasText: item.prompt.display_name }).click();
      await expect(editor.page.getByText(item.prompt.text, { exact: true })).toBeVisible();
      await editor.page.getByRole("button", { name: "Close", exact: true }).click();
    }
    log("Home search: current prompt definitions from all four spaces passed");

    await editor.page.goto(`${origin}/admin/self-test`);
    const family = editor.page.locator('[data-family="prompts"]');
    await expect(family).toBeVisible();
    await editor.page.screenshot({ path: "target/prompts-self-test.png", fullPage: true });
    for (const item of created) {
      await family.getByRole("button", { name: "Scenario space", exact: true }).click();
      await editor.page.getByRole("option").filter({ hasText: item.space.id }).click();
      await family.getByRole("button", { name: "Run", exact: true }).click();
      log(`Real prompt self-test launcher: ${item.space.kind} started`);
      await expect(family.getByRole("button", { name: "Run", exact: true })).toBeEnabled();
      const expand = family.getByRole("button", { name: "Show steps", exact: true });
      if (await expand.count()) await expand.click();
      if (await family.getByText("Failed", { exact: true }).count()) console.error(await family.innerText());
      await expect(family.getByText("Verified", { exact: true })).toBeVisible({ timeout: 1_000 });
      await expect(family).toContainText("0 failed");
      const remaining = await request(editor, "GET", item.collection);
      assert.deepEqual(
        remaining.items.map((p) => p.prompt_id),
        [item.prompt.prompt_id],
        "Self-test cleanup preserves pre-existing prompts",
      );
      log(`Real prompt self-test launcher: ${item.space.kind} passed`);
    }

    // Real roles, on collective spaces only. Never grant another person a role in a personal space.
    for (const username of ["carol", "elena", "alice", "oscar", "zoe", "bob"]) {
      actors[username] = await login(username, "Azerty123_", "/home");
    }
    for (const space of collective) {
      await request(editor, "PUT", `/spaces/${space.id}/roles/member/${subject(actors.carol)}`, 204);
      await request(editor, "DELETE", `/spaces/${space.id}/roles/editor/${subject(actors.carol)}`, 204);
      await request(editor, "PUT", `/spaces/${space.id}/roles/analyst/${subject(actors.elena)}`, 204);
      await request(editor, "PUT", `/spaces/${space.id}/roles/editor/${subject(actors.bob)}`, 204);
    }
    for (const [name, canRead] of [
      ["carol", true],
      ["elena", true],
      ["alice", false],
      ["oscar", false],
      ["zoe", false],
    ]) {
      const actor = actors[name];
      await actor.page.goto(`${origin}/admin/self-test`);
      await expect(actor.page.getByText("Unauthorized", { exact: true })).toBeVisible();
      await expect(actor.page.locator('[data-family="prompts"]')).toHaveCount(0);
      for (const item of created) {
        const readable = canRead && item.space.kind !== "personal";
        const denied = name === "zoe" ? 404 : 403;
        await request(actor, "GET", item.collection, readable ? 200 : denied);
        await request(actor, "GET", item.path, readable ? 200 : denied);
        await request(actor, "PATCH", item.path, denied, { display_name: "Forbidden edit" });
        await request(actor, "DELETE", item.path, denied);
        await request(actor, "POST", item.collection, denied, {
          logical_name: "denied",
          display_name: "Denied",
          text: "Denied",
        });
        const categoriesPath = `/spaces/${item.space.id}/prompt-categories`;
        await request(actor, "GET", categoriesPath, readable ? 200 : denied);
        await request(actor, "POST", categoriesPath, denied, { name: "Denied" });
        await request(actor, "DELETE", `${categoriesPath}/${item.category.id}`, denied);
        await request(actor, "PUT", `${item.path}/favorite`, readable ? 204 : denied);
        if (readable) {
          await request(actor, "DELETE", `${item.path}/favorite`, 204);
          assert.equal((await request(actor, "GET", item.path)).is_favorite, false);
          assert.equal((await request(editor, "GET", item.path)).is_favorite, true);
          await open(actor, item.space);
          await expect(actor.page.getByText(item.prompt.display_name, { exact: true })).toBeVisible();
          await expect(actor.page.getByRole("button", { name: "Create prompt", exact: true })).toHaveCount(0);
          await expect(actor.page.getByRole("button", { name: "Manage categories", exact: true })).toBeDisabled();
          await expect(actor.page.getByRole("button", { name: /^Actions for / })).toHaveCount(0);
          await actor.page.getByText(item.prompt.display_name, { exact: true }).click();
          await expect(actor.page.getByText(item.prompt.text, { exact: true })).toBeVisible();
          await actor.page.getByRole("button", { name: "Close", exact: true }).click();
        } else {
          await actor.page.goto(`${origin}/team/${item.space.id}/prompts`);
          await expect(
            actor.page.getByText("This space is unavailable or you do not have access.", { exact: true }),
          ).toBeVisible();
          await expect(actor.page.getByRole("button", { name: "Create prompt", exact: true })).toHaveCount(0);
          await expect(actor.page.getByText(item.prompt.display_name, { exact: true })).toHaveCount(0);
        }
      }
      log(`Prompt permissions: ${name} passed across four spaces`);
    }
    // A child owner must first hold content access in its parent. Test each level
    // before granting the parent membership needed to reach the next one.
    for (let index = 1; index < collective.length; index += 1) {
      const space = collective[index];
      const item = created.find((candidate) => candidate.space.id === space.id);
      await request(editor, "PUT", `/spaces/${collective[index - 1].id}/roles/member/${subject(actors.alice)}`, 204);
      await request(editor, "PUT", `/spaces/${space.id}/roles/owner/${subject(actors.alice)}`, 204);
      await request(actors.alice, "GET", item.path, 403);
      await request(actors.alice, "PATCH", item.path, 403, { display_name: "Owner is not editor" });
      await actors.alice.page.goto(`${origin}/team/${space.id}/prompts`);
      await expect(
        actors.alice.page.getByText("This space is unavailable or you do not have access.", { exact: true }),
      ).toBeVisible();
      log(`Prompt permissions: owner alone in ${space.kind} passed`);
    }

    const templates = await request(editor, "GET", `/organizations/${collective[0].id}/agents`);
    const native = templates.find((t) => t.name === "Ralph");
    assert(native, "Native agent is available for the composer reception");
    await request(editor, "PUT", `/organizations/${collective[0].id}/agents/${native.id}/default-on`, 200, {
      default_on: true,
    });
    for (const item of created.filter((i) => i.space.kind !== "organization")) {
      const agentPath = `/spaces/${item.space.id}/agent-instances`;
      const instance = await request(editor, "POST", agentPath, 201, {
        template_id: native.id,
        logical_name: "prompt_reception",
        display_name: "Prompt reception",
        usage_statement: "Check prompt insertion",
      });
      await editor.page.goto(`${origin}/team/${item.space.id}/managed-chat/${instance.agent_instance_id}`);
      await editor.page.getByRole("button", { name: "Prompt library", exact: true }).click();
      await editor.page.getByText(item.prompt.display_name, { exact: true }).click();
      const composer = editor.page.locator('[contenteditable="true"]');
      await expect(composer).toHaveText(item.prompt.text);
      await composer.fill("/acceptance");
      const commandGroup = editor.page.locator(
        `[data-source="${item.space.kind === "personal" ? "personal" : "team"}"]`,
      );
      await expect(commandGroup.getByRole("option").filter({ hasText: "/acceptance" })).toBeVisible();
      await editor.page.screenshot({ path: `target/prompts-composer-${item.space.kind}.png`, fullPage: true });
      await editor.page.goto(`${origin}/home`);
      await request(editor, "DELETE", `${agentPath}/${instance.agent_instance_id}`, 204);
      log(`Real composer insertion and slash menu: ${item.space.kind} passed`);
    }

    for (const item of created) {
      await request(root, "GET", item.path, 404); // Platform administration is not business content access.
      const deleter = item.space.kind === "personal" ? editor : actors.bob;
      if (deleter !== editor) {
        await request(editor, "DELETE", `/spaces/${item.space.id}/roles/editor/${subject(editor)}`, 204);
        await request(editor, "PATCH", item.path, 403, { description: "Author has no special write right" });
        await request(deleter, "PATCH", item.path, 200, { description: "Maintained by another editor" });
        const retained = await request(deleter, "GET", item.path);
        assert.equal(retained.created_by, subject(editor));
      }
      await open(deleter, item.space);
      await action(deleter.page, item.prompt.display_name, "Delete");
      const dialog = deleter.page.getByRole("alertdialog", { name: "Delete prompt?", exact: true });
      await exchange(
        deleter.page,
        "DELETE",
        item.path,
        () => dialog.getByRole("button", { name: "Delete", exact: true }).click(),
        204,
      );
      await request(deleter, "GET", item.path, 404);
      await request(deleter, "DELETE", `/spaces/${item.space.id}/prompt-categories/${item.category.id}`, 204);
    }
    log(
      "Prompt browser reception passed: four spaces, collective reader/analyst/editor, owner/admin isolation, personal privacy, cross-organization isolation and another editor's maintenance/deletion.",
    );
  } catch (error) {
    for (const [name, actor] of Object.entries(actors)) {
      await actor.page.screenshot({ path: `target/prompts-failure-${name}.png`, fullPage: true }).catch(() => {});
      console.error(
        `${name}: ${await actor.page
          .locator("body")
          .innerText()
          .catch(() => "page unavailable")}`,
      );
    }
    throw error;
  }
}

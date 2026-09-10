import assert from "node:assert/strict";
import { createServer } from "node:http";
import { fileURLToPath } from "node:url";
import { mkdir, readFile, stat, writeFile } from "node:fs/promises";
import path from "node:path";

import { chromium } from "@playwright/test";

import { workspaceRoot } from "./pack-design-tokens.mjs";

function optionValue(name) {
  const index = process.argv.indexOf(name);
  return index === -1 ? undefined : process.argv[index + 1];
}

function contentType(filePath) {
  const extension = path.extname(filePath);
  return (
    {
      ".css": "text/css; charset=utf-8",
      ".html": "text/html; charset=utf-8",
      ".js": "text/javascript; charset=utf-8",
      ".woff2": "font/woff2",
    }[extension] ?? "application/octet-stream"
  );
}

async function startServer(outputRoot, defaultFile = "tokens-only.html") {
  const server = createServer(async (request, response) => {
    try {
      const url = new URL(request.url ?? "/", "http://127.0.0.1");
      const requestedPath =
        url.pathname === "/" ? `/${defaultFile}` : url.pathname;
      const filePath = path.resolve(
        outputRoot,
        `.${decodeURIComponent(requestedPath)}`,
      );
      const relativePath = path.relative(outputRoot, filePath);
      if (relativePath.startsWith("..") || path.isAbsolute(relativePath)) {
        response.writeHead(403).end("Forbidden");
        return;
      }
      const fileStat = await stat(filePath);
      if (!fileStat.isFile()) {
        response.writeHead(404).end("Not found");
        return;
      }
      response.writeHead(200, {
        "Cache-Control": "no-store",
        "Content-Type": contentType(filePath),
      });
      response.end(await readFile(filePath));
    } catch {
      response.writeHead(404).end("Not found");
    }
  });
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  const address = server.address();
  assert(address && typeof address === "object");
  return {
    origin: `http://127.0.0.1:${address.port}`,
    close: () =>
      new Promise((resolve, reject) =>
        server.close((error) => (error ? reject(error) : resolve())),
      ),
  };
}

async function createObservedPage(browser, allowedOrigins) {
  const origins = new Set(
    Array.isArray(allowedOrigins) ? allowedOrigins : [allowedOrigins],
  );
  const context = await browser.newContext({ serviceWorkers: "block" });
  const requests = [];
  const blockedRequests = [];
  const requestFailures = [];
  const responses = [];
  await context.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const record = { type: request.resourceType(), url: request.url() };
    requests.push(record);
    if (!origins.has(url.origin) || url.protocol !== "http:") {
      blockedRequests.push(record);
      await route.abort("blockedbyclient");
      return;
    }
    await route.continue();
  });
  const page = await context.newPage();
  page.on("requestfailed", (request) => {
    requestFailures.push({
      errorText: request.failure()?.errorText ?? "unknown failure",
      type: request.resourceType(),
      url: request.url(),
    });
  });
  page.on("response", (response) => {
    responses.push({
      status: response.status(),
      type: response.request().resourceType(),
      url: response.url(),
    });
  });
  return {
    context,
    page,
    requests,
    blockedRequests,
    requestFailures,
    responses,
  };
}

export function assertSuccessfulBrowserRequests(observation) {
  assert.deepEqual(observation.requestFailures, [], "browser request failed");
  for (const response of observation.responses) {
    assert(
      response.status >= 200 && response.status < 300,
      `browser received unsuccessful HTTP ${response.status} for ${response.url}`,
    );
  }
}

export async function assertBrowserPrerequisites({
  browserPath = chromium.executablePath(),
  tokenOutput = path.join(workspaceRoot, "target/staged-consumers/tokens"),
  reactOutput = path.join(workspaceRoot, "target/staged-consumers/react"),
  iframeSdkOutput = path.join(
    workspaceRoot,
    "target/staged-consumers/iframe-sdk",
  ),
} = {}) {
  await Promise.all([
    stat(path.join(tokenOutput, "tokens-only.html")).catch(() => {
      throw new Error(
        "staged token consumer is missing; run npm run test:consumer first",
      );
    }),
    stat(path.join(reactOutput, "index.html")).catch(() => {
      throw new Error(
        "staged React consumer is missing; run npm run test:consumer first",
      );
    }),
    ...["index.html", "child.html", "attacker.html"].map((file) =>
      stat(path.join(iframeSdkOutput, file)).catch(() => {
        throw new Error(
          "staged iframe SDK consumer is missing; run npm run test:consumer first",
        );
      }),
    ),
    stat(browserPath).catch(() => {
      throw new Error(
        "Playwright Chromium is missing; run npm run browser:install during provisioning",
      );
    }),
  ]);
}

function assertLocalRequests(observation, allowedOrigins) {
  const origins = new Set(
    Array.isArray(allowedOrigins) ? allowedOrigins : [allowedOrigins],
  );
  assertSuccessfulBrowserRequests(observation);
  assert.deepEqual(
    observation.blockedRequests,
    [],
    "browser attempted a non-loopback request",
  );
  for (const request of observation.requests) {
    assert(origins.has(new URL(request.url).origin));
    assert(
      !request.url.startsWith("file:"),
      `browser requested a file URL: ${request.url}`,
    );
    assert(
      !request.url.includes("apps/frontend"),
      `browser requested a FRED source path: ${request.url}`,
    );
    assert(
      !request.url.includes("fred-frontend-packaging"),
      `browser exposed the FRED checkout path: ${request.url}`,
    );
  }
}

async function iframeHarness(page) {
  await page.waitForFunction(() => window.__fredHost?.readyCount >= 2);
  let child;
  let attacker;
  for (let attempt = 0; attempt < 100; attempt += 1) {
    child = page.frames().find((frame) => /\/child\.html/.test(frame.url()));
    attacker = page
      .frames()
      .find((frame) => /\/attacker\.html/.test(frame.url()));
    if (child && attacker) break;
    await page.waitForTimeout(10);
  }
  assert(
    child,
    `cross-origin child frame is missing: ${page
      .frames()
      .map((frame) => frame.url())
      .join(", ")}`,
  );
  assert(
    attacker,
    `cross-origin attacker frame is missing: ${page
      .frames()
      .map((frame) => frame.url())
      .join(", ")}`,
  );
  await child.waitForFunction(() => window.__fredChild !== undefined);
  await child.evaluate(async () => window.__fredChild.connected);
  return { attacker, child };
}

async function rejectedIframeHarness(page) {
  let child;
  for (let attempt = 0; attempt < 100 && !child; attempt += 1) {
    child = page
      .frames()
      .find(
        (frame) =>
          frame.url() && new URL(frame.url()).pathname === "/child.html",
      );
    if (!child) await page.waitForTimeout(10);
  }
  assert(child, "negative cross-origin child frame is missing");
  await child.waitForFunction(() => window.__fredChild !== undefined);
  await child.waitForFunction(
    () => window.__fredChild.connectionError !== null,
  );
  return child.evaluate(() => window.__fredChild.connectionError);
}

async function verifyIframeSdk(
  browser,
  hostOrigin,
  applicationOrigin,
  attackerOrigin,
) {
  const allowedOrigins = [hostOrigin, applicationOrigin, attackerOrigin];
  const observation = await createObservedPage(browser, allowedOrigins);
  try {
    await observation.page.goto(
      `${hostOrigin}/?applicationOrigin=${encodeURIComponent(applicationOrigin)}&attackerOrigin=${encodeURIComponent(attackerOrigin)}`,
      { waitUntil: "networkidle" },
    );
    let { attacker, child } = await iframeHarness(observation.page);
    const admission = await observation.page.evaluate(() => ({
      applicationOrigin: window.__fredHost.applicationOrigin,
      readyCount: window.__fredHost.readyCount,
      protocolVersion: window.__fredHost.records.find(
        (message) => message.type === "fred:ready",
      )?.protocolVersion,
    }));
    assert.equal(admission.applicationOrigin, applicationOrigin);
    assert(admission.readyCount >= 2, "ready retry was not observed");
    assert.equal(admission.protocolVersion, "1");

    await observation.page.evaluate(() => window.__fredHost.sendRoute("A"));
    await child.evaluate(() => window.__fredChild.navigate("B"));
    await observation.page.evaluate(() => window.__fredHost.sendRoute("A"));
    await child.waitForFunction(() => window.__fredChild.routes.length === 2);
    assert.deepEqual(await child.evaluate(() => window.__fredChild.routes), [
      "A",
      "A",
    ]);
    await child.evaluate(() => window.__fredChild.openChat("session-1"));
    const intents = await observation.page.evaluate(() =>
      window.__fredHost.records.filter(
        (message) =>
          message.type === "fred:navigate" || message.type === "fred:open-chat",
      ),
    );
    assert.deepEqual(intents, [
      { type: "fred:navigate", path: "B", replace: false },
      { type: "fred:open-chat", sessionId: "session-1" },
    ]);

    assert.deepEqual(
      await child.evaluate(() => window.__fredChild.requestPair()),
      ["pair/one", "pair/two"],
    );
    for (const [pathName, method, expected] of [
      ["ok", "GET", { status: 200, text: '{"ok":true}' }],
      ["status/401", "GET", { status: 401, text: '{"ok":false}' }],
      ["status/403", "GET", { status: 403, text: '{"ok":false}' }],
      ["status/503", "GET", { status: 503, text: '{"ok":false}' }],
      ["status/204", "GET", { status: 204, text: "" }],
      ["status/205", "GET", { status: 205, text: "" }],
      ["status/304", "GET", { status: 304, text: "" }],
      ["ok", "HEAD", { status: 200, text: "" }],
    ]) {
      const result = await child.evaluate(
        ([requestPath, requestMethod]) =>
          window.__fredChild.request(requestPath, requestMethod),
        [pathName, method],
      );
      assert.deepEqual(
        { status: result.status, text: result.text },
        expected,
        `${method} ${pathName}`,
      );
      assert.equal(result.headers["x-fred-fixture"], "local");
    }
    assert.deepEqual(
      await child.evaluate(() => window.__fredChild.request("transport-error")),
      { code: "transport-error" },
    );
    assert.deepEqual(
      await child.evaluate(() =>
        window.__fredChild.request("settlement/duplicate"),
      ),
      {
        status: 200,
        headers: {},
        text: "first",
      },
    );
    assert.deepEqual(
      await child.evaluate(() =>
        window.__fredChild.request("settlement/unknown"),
      ),
      {
        status: 200,
        headers: {
          "content-type": "application/json",
          "x-fred-fixture": "local",
        },
        text: '{"ok":true}',
      },
    );
    assert.deepEqual(
      await child.evaluate(() =>
        window.__fredChild.request("pending/timeout", "GET", 10),
      ),
      { code: "request-timeout" },
    );
    assert.deepEqual(
      await child.evaluate(() =>
        window.__fredChild.request("pending/late", "GET", 10),
      ),
      { code: "request-timeout" },
    );
    await observation.page.waitForTimeout(60);
    assert.deepEqual(
      await child.evaluate(() => window.__fredChild.request("after-late")),
      {
        status: 200,
        headers: {
          "content-type": "application/json",
          "x-fred-fixture": "local",
        },
        text: '{"ok":true}',
      },
    );
    assert.equal(
      await child.evaluate(() => window.__fredChild.abort()),
      "AbortError",
    );

    const routeCount = await child.evaluate(
      () => window.__fredChild.routes.length,
    );
    await observation.page.evaluate(() =>
      window.__fredHost.send({ type: "fred:route", subPath: 7 }),
    );
    await attacker.evaluate(() =>
      window.__attack({ type: "fred:route", subPath: "attacker" }),
    );
    await observation.page.waitForTimeout(20);
    assert.equal(
      await child.evaluate(() => window.__fredChild.routes.length),
      routeCount,
      "malformed or impersonated route was admitted",
    );
    assert(
      (await observation.page.evaluate(() => window.__fredHost.rejected)) >= 1,
      "host did not reject the attacker frame",
    );

    const hostRecordCount = await observation.page.evaluate(
      () => window.__fredHost.records.length,
    );
    assert.deepEqual(
      await child.evaluate(() => window.__fredChild.invalidInputs()),
      ["TypeError", "invalid-request"],
    );
    assert.equal(
      await observation.page.evaluate(() => window.__fredHost.records.length),
      hostRecordCount,
      "unsafe path or protected header reached the host",
    );

    const rejectedConnections = {};
    for (const mode of ["malformed", "unsupported", "mismatch"]) {
      await observation.page.evaluate((selectedMode) => {
        window.__fredHost.configureContext(selectedMode);
        window.__fredHost.replaceFrame(100);
      }, mode);
      rejectedConnections[mode] = await rejectedIframeHarness(observation.page);
    }
    await observation.page.evaluate(() => {
      window.__fredHost.configureContext("silent");
      window.__fredHost.replaceFrame(30);
    });
    rejectedConnections.deadline = await rejectedIframeHarness(
      observation.page,
    );
    assert.match(rejectedConnections.malformed, /malformed/i);
    assert.match(rejectedConnections.unsupported, /unsupported/i);
    assert.match(rejectedConnections.mismatch, /different application/i);
    assert.match(rejectedConnections.deadline, /deadline/i);

    await observation.page.evaluate(() => {
      window.__fredHost.configureContext("valid", "team-2");
      window.__fredHost.replaceFrame();
    });
    ({ attacker, child } = await iframeHarness(observation.page));
    assert.equal(
      await child.evaluate(() => window.__fredChild.client.context?.team.id),
      "team-2",
    );
    assert.equal(
      await child.evaluate(() => window.__fredChild.capacity()),
      "request-capacity",
    );
    const disposedRoutes = await child.evaluate(
      () => window.__fredChild.routes.length,
    );
    await observation.page.evaluate(() =>
      window.__fredHost.sendRoute("after-disposal"),
    );
    await observation.page.waitForTimeout(20);
    assert.equal(
      await child.evaluate(() => window.__fredChild.routes.length),
      disposedRoutes,
    );

    assertLocalRequests(observation, allowedOrigins);
    return {
      admission,
      intents,
      routes: ["A", "A"],
      rejectedConnections,
      crossOrigin: hostOrigin !== applicationOrigin,
      attackerOriginDistinct: attackerOrigin !== applicationOrigin,
      requests: observation.requests,
      responses: observation.responses,
    };
  } finally {
    await observation.context.close();
  }
}

async function verifyTokens(browser, origin) {
  const observation = await createObservedPage(browser, origin);
  try {
    await observation.page.goto(`${origin}/tokens-only.html`, {
      waitUntil: "networkidle",
    });
    const themes = {};
    for (const theme of ["light", "dark"]) {
      themes[theme] = await observation.page.evaluate((selectedTheme) => {
        document.documentElement.dataset.theme = selectedTheme;
        const style = getComputedStyle(document.querySelector("#probe"));
        return {
          backgroundColor: style.backgroundColor,
          borderRadius: style.borderRadius,
          color: style.color,
          fontFamily: style.fontFamily,
          fontSize: style.fontSize,
          fontWeight: style.fontWeight,
          padding: style.padding,
        };
      }, theme);
    }
    assert.deepEqual(themes.light, {
      backgroundColor: "rgb(251, 248, 255)",
      borderRadius: "8px",
      color: "rgb(25, 27, 33)",
      fontFamily: "Geist, sans-serif",
      fontSize: "14px",
      fontWeight: "400",
      padding: "16px",
    });
    assert.deepEqual(themes.dark, {
      backgroundColor: "rgb(17, 19, 24)",
      borderRadius: "8px",
      color: "rgb(240, 239, 250)",
      fontFamily: "Geist, sans-serif",
      fontSize: "14px",
      fontWeight: "400",
      padding: "16px",
    });
    const shellOwnership = await observation.page.evaluate(() => ({
      documentOverflow: getComputedStyle(document.documentElement).overflow,
      bodyOverflow: getComputedStyle(document.body).overflow,
      bodyUserSelect: getComputedStyle(document.body).userSelect,
      outsideBoxSizing: getComputedStyle(
        document.querySelector("#outside-probe"),
      ).boxSizing,
    }));
    assert.deepEqual(shellOwnership, {
      documentOverflow: "visible",
      bodyOverflow: "visible",
      bodyUserSelect: "text",
      outsideBoxSizing: "content-box",
    });
    assert.deepEqual(
      observation.requests.filter(
        ({ type, url }) => type === "font" || url.endsWith(".woff2"),
      ),
      [],
      "fresh tokens-only consumer requested a font",
    );
    assertLocalRequests(observation, origin);
    return {
      themes,
      shellOwnershipBeforeUiStyles: shellOwnership,
      requests: observation.requests,
      requestFailures: observation.requestFailures,
      responses: observation.responses,
    };
  } finally {
    await observation.context.close();
  }
}

async function verifyFonts(browser, origin) {
  const observation = await createObservedPage(browser, origin);
  try {
    await observation.page.goto(`${origin}/fonts.html`, {
      waitUntil: "networkidle",
    });
    const loaded = await observation.page.evaluate(async () => {
      const regular = await document.fonts.load(
        '400 32px "Geist"',
        "Regular Geist probe",
      );
      const italic = await document.fonts.load(
        'italic 400 32px "Geist"',
        "Italic Geist probe",
      );
      return {
        italic:
          italic.length > 0 && document.fonts.check('italic 400 32px "Geist"'),
        italicStyle: getComputedStyle(document.querySelector("#italic"))
          .fontStyle,
        regular: regular.length > 0 && document.fonts.check('400 32px "Geist"'),
        regularStyle: getComputedStyle(document.querySelector("#regular"))
          .fontStyle,
      };
    });
    assert.deepEqual(loaded, {
      italic: true,
      italicStyle: "italic",
      regular: true,
      regularStyle: "normal",
    });
    const fontRequests = observation.requests.filter(
      ({ type, url }) => type === "font" || url.endsWith(".woff2"),
    );
    assert.deepEqual(
      fontRequests.map(({ url }) => new URL(url).pathname).sort(),
      ["/fonts/Geist-Italic.woff2", "/fonts/Geist.woff2"],
    );
    for (const request of fontRequests) {
      assert(
        observation.responses.some(
          ({ status, url }) => status === 200 && url === request.url,
        ),
        `font did not load successfully: ${request.url}`,
      );
    }
    assertLocalRequests(observation, origin);
    return {
      loaded,
      fontRequests,
      requests: observation.requests,
      requestFailures: observation.requestFailures,
      responses: observation.responses,
    };
  } finally {
    await observation.context.close();
  }
}

async function verifyUi(browser, origin) {
  const observation = await createObservedPage(browser, origin);
  try {
    await observation.page.goto(origin, { waitUntil: "networkidle" });
    const themes = {};
    for (const theme of ["light", "dark"]) {
      themes[theme] = await observation.page.evaluate((selectedTheme) => {
        document.documentElement.dataset.theme = selectedTheme;
        const shell = getComputedStyle(document.querySelector("main"));
        const snapshot = (selector) => {
          const style = getComputedStyle(document.querySelector(selector));
          return {
            backgroundColor: style.backgroundColor,
            borderColor: style.borderColor,
            color: style.color,
            fontFamily: style.fontFamily,
            fontSize: style.fontSize,
          };
        };
        return {
          shell: {
            backgroundColor: shell.backgroundColor,
            color: shell.color,
          },
          Button: snapshot(".consumer-button"),
          IconButton: snapshot(".consumer-icon-button"),
          Icon: snapshot('[role="img"]'),
          TextInput: snapshot("#project-name"),
          Spinner: snapshot('svg[role="status"]'),
        };
      }, theme);
    }
    assert.deepEqual(themes.light.shell, {
      backgroundColor: "rgb(251, 248, 255)",
      color: "rgb(25, 27, 33)",
    });
    assert.deepEqual(themes.dark.shell, {
      backgroundColor: "rgb(17, 19, 24)",
      color: "rgb(240, 239, 250)",
    });
    for (const component of [
      "Button",
      "IconButton",
      "Icon",
      "TextInput",
      "Spinner",
    ]) {
      assert(
        Object.values(themes.light[component]).every(Boolean) &&
          Object.values(themes.dark[component]).every(Boolean),
        `${component} lacks representative computed styles`,
      );
      assert.notDeepEqual(
        themes.light[component],
        themes.dark[component],
        `${component} did not consume light/dark theme values`,
      );
    }
    const shellOwnership = await observation.page.evaluate(() => ({
      documentOverflow: getComputedStyle(document.documentElement).overflow,
      bodyOverflow: getComputedStyle(document.body).overflow,
      bodyUserSelect: getComputedStyle(document.body).userSelect,
      outsideBoxSizing: getComputedStyle(
        document.querySelector("#outside-probe"),
      ).boxSizing,
      insideBoxSizing: getComputedStyle(document.querySelector("main"))
        .boxSizing,
      escapedComponentNodes: [
        ...document.querySelectorAll("button, input, svg"),
      ].filter((element) => !element.closest(".fred-ui")).length,
    }));
    assert.deepEqual(shellOwnership, {
      documentOverflow: "visible",
      bodyOverflow: "visible",
      bodyUserSelect: "text",
      outsideBoxSizing: "content-box",
      insideBoxSizing: "border-box",
      escapedComponentNodes: 0,
    });

    const save = observation.page.getByRole("button", { name: /^Save/ });
    await observation.page.keyboard.press("Tab");
    assert.equal(
      await save.evaluate((element) => element === document.activeElement),
      true,
    );
    await observation.page.keyboard.press("Enter");
    assert.equal(
      await observation.page.locator("main").getAttribute("data-clicks"),
      "1",
    );
    const iconButton = observation.page.getByRole("button", {
      name: "Add item",
    });
    await observation.page.keyboard.press("Tab");
    assert.equal(
      await iconButton.evaluate(
        (element) => element === document.activeElement,
      ),
      true,
      "Tab did not skip the disabled button and reach IconButton",
    );
    const iconButtonEvidence = await iconButton.evaluate((element) => ({
      className: element.className,
      outlineColor: getComputedStyle(element).outlineColor,
      outlineStyle: getComputedStyle(element).outlineStyle,
      outlineWidth: getComputedStyle(element).outlineWidth,
    }));
    assert(iconButtonEvidence.className.includes("consumer-icon-button"));
    assert(
      iconButtonEvidence.className.split(" ").length >= 5,
      "generated IconButton classes are missing",
    );
    assert.notEqual(iconButtonEvidence.outlineColor, "rgba(0, 0, 0, 0)");
    assert.notEqual(iconButtonEvidence.outlineStyle, "none");
    await observation.page.keyboard.press("Space");
    assert.equal(
      await observation.page.locator("main").getAttribute("data-clicks"),
      "2",
    );
    await observation.page.keyboard.press("Tab");
    assert.equal(
      await observation.page
        .locator("#project-name")
        .evaluate((element) => element === document.activeElement),
      true,
      "Tab did not reach TextInput",
    );

    assert.equal(
      await observation.page
        .getByRole("img", { name: "Search symbol" })
        .count(),
      1,
    );
    assert.equal(
      await observation.page
        .locator('.material-symbols-outlined[aria-label="info"]')
        .count(),
      0,
    );
    const invalid = observation.page.locator("#invalid-name");
    assert.equal(await invalid.getAttribute("aria-invalid"), "true");
    const errorId = await invalid.getAttribute("aria-describedby");
    assert(
      errorId &&
        (await observation.page.locator(`#${errorId}`).textContent()) ===
          "A name is required",
    );
    assert.equal(
      await observation.page.locator("#disabled-name").isDisabled(),
      true,
    );
    const loading = observation.page.getByRole("button", {
      name: "Downloading",
    });
    assert.equal(await loading.isDisabled(), true);
    assert.equal(await loading.getAttribute("aria-busy"), "true");
    const disabledAction = observation.page.getByRole("button", {
      name: "Disabled action",
    });
    assert.equal(await disabledAction.isDisabled(), true);
    await disabledAction.evaluate((element) => element.click());
    await loading.evaluate((element) => element.click());
    assert.equal(
      await observation.page.locator("main").getAttribute("data-clicks"),
      "2",
      "disabled/loading controls activated",
    );
    assert.equal(
      await observation.page.getByRole("status", { name: "Loading" }).count(),
      2,
    );
    assert.equal(
      await observation.page
        .getByRole("status", { name: "Saving package" })
        .count(),
      1,
    );

    const resetFixture = observation.page.getByRole("form", {
      name: "Reset counter fixture",
    });
    const resetInput = resetFixture.getByLabel("Resettable name");
    await resetInput.fill("abcdef");
    await resetFixture.getByText("6 / 20").waitFor();
    await resetFixture.getByRole("button", { name: "Reset counter" }).click();
    assert.equal(await resetFixture.getAttribute("data-reset-count"), "1");
    assert.equal(await resetInput.inputValue(), "abc");
    await resetFixture.getByText("3 / 20").waitFor();
    const resetCounter = {
      count: await resetFixture.getByText("3 / 20").textContent(),
      parentResetCount: await resetFixture.getAttribute("data-reset-count"),
      value: await resetInput.inputValue(),
    };

    const tonalStates = {};
    for (const name of ["Surface tonal", "Retreat tonal"]) {
      const button = observation.page.getByRole("button", { name });
      const stateLayer = button.locator("div").first();
      const resting = await stateLayer.evaluate(
        (element) => getComputedStyle(element).backgroundColor,
      );
      await button.hover();
      const hover = await stateLayer.evaluate(
        (element) => getComputedStyle(element).backgroundColor,
      );
      await observation.page.mouse.down();
      const pressed = await stateLayer.evaluate(
        (element) => getComputedStyle(element).backgroundColor,
      );
      await observation.page.mouse.up();
      assert.notEqual(hover, resting, `${name} has no hover state layer`);
      assert.notEqual(pressed, resting, `${name} has no pressed state layer`);
      assert.notEqual(
        pressed,
        hover,
        `${name} hover and pressed states are identical`,
      );
      tonalStates[name] = { resting, hover, pressed };
    }

    const materialLoaded = await observation.page.evaluate(async () => {
      await document.fonts.load('24px "Material Symbols Outlined"', "search");
      return document.fonts.check('24px "Material Symbols Outlined"', "search");
    });
    assert.equal(materialLoaded, true);
    const fontRequests = observation.requests.filter(
      ({ type, url }) => type === "font" || url.endsWith(".woff2"),
    );
    assert.equal(
      fontRequests.length,
      1,
      "UI consumer must request only the packaged Material Symbols font",
    );
    assert(fontRequests[0].url.includes("MaterialSymbolsOutlined"));
    assert.equal(
      fontRequests.some(({ url }) =>
        /Geist|fonts\.gstatic|fonts\.googleapis/i.test(url),
      ),
      false,
    );
    assertLocalRequests(observation, origin);
    return {
      themes,
      shellOwnership,
      iconButton: iconButtonEvidence,
      resetCounter,
      tonalStates,
      materialLoaded,
      fontRequests,
      requests: observation.requests,
      responses: observation.responses,
    };
  } finally {
    await observation.context.close();
  }
}

export async function runBrowserSmoke({ evidencePath } = {}) {
  const tokenOutput = path.join(
    workspaceRoot,
    "target/staged-consumers/tokens",
  );
  const reactOutput = path.join(workspaceRoot, "target/staged-consumers/react");
  const iframeSdkOutput = path.join(
    workspaceRoot,
    "target/staged-consumers/iframe-sdk",
  );
  await assertBrowserPrerequisites({
    tokenOutput,
    reactOutput,
    iframeSdkOutput,
  });
  let tokenServer;
  let reactServer;
  let iframeHostServer;
  let iframeChildServer;
  let iframeAttackerServer;
  let browser;
  try {
    tokenServer = await startServer(tokenOutput);
    reactServer = await startServer(reactOutput, "index.html");
    iframeHostServer = await startServer(iframeSdkOutput, "index.html");
    iframeChildServer = await startServer(iframeSdkOutput, "child.html");
    iframeAttackerServer = await startServer(iframeSdkOutput, "attacker.html");
    browser = await chromium.launch({ headless: true });
    const [tokens, fonts, ui, iframeSdk] = await Promise.all([
      verifyTokens(browser, tokenServer.origin),
      verifyFonts(browser, tokenServer.origin),
      verifyUi(browser, reactServer.origin),
      verifyIframeSdk(
        browser,
        iframeHostServer.origin,
        iframeChildServer.origin,
        iframeAttackerServer.origin,
      ),
    ]);
    for (const property of [
      "documentOverflow",
      "bodyOverflow",
      "bodyUserSelect",
      "outsideBoxSizing",
    ])
      assert.equal(
        ui.shellOwnership[property],
        tokens.shellOwnershipBeforeUiStyles[property],
        `UI style import changed consumer-owned ${property}`,
      );
    const evidence = {
      browser: "Playwright Chromium (pre-provisioned)",
      dependencyInstallations: 0,
      browserProvisioning: 0,
      externalRequests: 0,
      tokensOnly: tokens,
      fontsOptIn: fonts,
      ui,
      iframeSdk,
      shellOwnershipComparison: {
        beforeUiStyles: tokens.shellOwnershipBeforeUiStyles,
        afterUiStyles: ui.shellOwnership,
      },
    };
    if (evidencePath) {
      const resolvedEvidence = path.resolve(workspaceRoot, evidencePath);
      await mkdir(path.dirname(resolvedEvidence), { recursive: true });
      await writeFile(
        resolvedEvidence,
        `${JSON.stringify(evidence, null, 2)}\n`,
      );
    }
    return evidence;
  } finally {
    await browser?.close();
    await tokenServer?.close();
    await reactServer?.close();
    await iframeHostServer?.close();
    await iframeChildServer?.close();
    await iframeAttackerServer?.close();
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  process.stdout.write(
    `${JSON.stringify(await runBrowserSmoke({ evidencePath: optionValue("--evidence") }), null, 2)}\n`,
  );
}

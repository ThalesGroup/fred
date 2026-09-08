import assert from "node:assert/strict";
import { createServer } from "node:http";
import { fileURLToPath } from "node:url";
import { mkdir, readFile, stat, writeFile } from "node:fs/promises";
import path from "node:path";

import { chromium } from "@playwright/test";

import { stageIsolatedConsumer } from "./isolated-consumer.mjs";
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
      ".woff2": "font/woff2",
    }[extension] ?? "application/octet-stream"
  );
}

async function startServer(outputRoot) {
  const server = createServer(async (request, response) => {
    try {
      const url = new URL(request.url ?? "/", "http://127.0.0.1");
      const requestedPath =
        url.pathname === "/" ? "/tokens-only.html" : url.pathname;
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

async function createObservedPage(browser, origin) {
  const context = await browser.newContext({ serviceWorkers: "block" });
  const requests = [];
  const blockedRequests = [];
  const responses = [];
  await context.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const record = { type: request.resourceType(), url: request.url() };
    requests.push(record);
    if (url.origin !== origin || url.protocol !== "http:") {
      blockedRequests.push(record);
      await route.abort("blockedbyclient");
      return;
    }
    await route.continue();
  });
  const page = await context.newPage();
  page.on("response", (response) => {
    responses.push({ status: response.status(), url: response.url() });
  });
  return { context, page, requests, blockedRequests, responses };
}

function assertLocalRequests(observation, origin) {
  assert.deepEqual(
    observation.blockedRequests,
    [],
    "browser attempted a non-loopback request",
  );
  for (const request of observation.requests) {
    assert.equal(new URL(request.url).origin, origin);
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
    assert.deepEqual(
      observation.requests.filter(
        ({ type, url }) => type === "font" || url.endsWith(".woff2"),
      ),
      [],
      "fresh tokens-only consumer requested a font",
    );
    assertLocalRequests(observation, origin);
    return { themes, requests: observation.requests };
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
    return { loaded, fontRequests, requests: observation.requests };
  } finally {
    await observation.context.close();
  }
}

export async function runBrowserSmoke({ evidencePath } = {}) {
  const staged = await stageIsolatedConsumer({ keep: true });
  let server;
  let browser;
  try {
    server = await startServer(staged.outputRoot);
    browser = await chromium.launch({ headless: true });
    const [tokens, fonts] = await Promise.all([
      verifyTokens(browser, server.origin),
      verifyFonts(browser, server.origin),
    ]);
    const evidence = {
      browser: "Playwright Chromium (pre-provisioned)",
      origin: server.origin,
      externalRequests: 0,
      tokensOnly: tokens,
      fontsOptIn: fonts,
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
    await server?.close();
    await staged.cleanup();
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  process.stdout.write(
    `${JSON.stringify(await runBrowserSmoke({ evidencePath: optionValue("--evidence") }), null, 2)}\n`,
  );
}

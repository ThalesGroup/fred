// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { once } from "node:events";
import { copyFile, mkdtemp, readFile, readdir, rm, writeFile } from "node:fs/promises";
import http from "node:http";
import { tmpdir } from "node:os";
import path from "node:path";
import { after, before, test } from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";
import { themeOverlayMiddleware, themeOverlayPlugin } from "./theme-overlay.mjs";

let fixtures;
before(async () => {
  fixtures = await mkdtemp(path.join(tmpdir(), "fred-theme-tests-"));
  execFileSync("python3", [
    "-c",
    `
import zipfile, json, sys
root=sys.argv[1]
with zipfile.ZipFile(root+'/valid.zip','w') as z:
    z.writestr('brand/theme-custom.css','body { color: red; }')
    z.writestr('brand/theme-properties.json',json.dumps({'siteTitle':'Paris Airport'}))
    z.writestr('brand/theme-catalog.json',json.dumps({'themes':[{'id':'paris','label':'Paris','base':'cobalt'}]}))
    z.writestr('brand/theme-translations/fr.json',json.dumps({'rework':{'home':{'greeting':'Bienvenue'}}}))
    z.writestr('brand/images/logo.svg','<svg>Paris</svg>')
    z.writestr('brand/images/font.ttf','font-bytes')
    z.writestr('brand/index.html','untrusted shell')
with zipfile.ZipFile(root+'/invalid.zip','w') as z:
    z.writestr('theme-properties.json',json.dumps({'user_auth':'forbidden'}))
with zipfile.ZipFile(root+'/blank-label.zip','w') as z:
    z.writestr('theme-catalog.json',json.dumps({'themes':[{'id':'acme','label':'   ','base':'cobalt'}]}))
with zipfile.ZipFile(root+'/escaping.zip','w') as z:
    z.writestr('../theme-custom.css','escaping')
with zipfile.ZipFile(root+'/symlink.zip','w') as z:
    z.writestr('theme-custom.css','valid')
    info=zipfile.ZipInfo('images/leak.svg')
    info.create_system=3
    info.external_attr=0o120777 << 16
    z.writestr(info,'/etc/passwd')
`,
    fixtures,
  ]);
});
after(async () => rm(fixtures, { recursive: true, force: true }));

async function start(environment) {
  let middleware;
  const messages = [];
  const server = http.createServer((request, response) => {
    const fallback = () => response.end("stock");
    if (middleware) middleware(request, response, fallback);
    else fallback();
  });
  const plugin = themeOverlayPlugin({
    FRONTEND_THEME_URL: "",
    FRONTEND_THEME_S3_ACCESS_KEY: "",
    FRONTEND_THEME_S3_SECRET_KEY: "",
    FRONTEND_THEME_REQUIRED: "false",
    ...environment,
  });
  try {
    await plugin.configureServer({
      config: { logger: { info: (m) => messages.push(m), warn: (m) => messages.push(m) } },
      middlewares: {
        use: (m) => {
          middleware = m;
        },
      },
      httpServer: server,
    });
  } catch (error) {
    server.close();
    throw error;
  }
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  return {
    url: `http://127.0.0.1:${server.address().port}`,
    messages,
    close: async () => {
      server.close();
      await once(server, "close");
    },
  };
}

const archiveUrl = (name) => pathToFileURL(path.join(fixtures, name)).href;

test("valid wrapped ZIP overlays files, sets MIME and falls back for missing/protected files", async () => {
  const app = await start({ FRONTEND_THEME_URL: archiveUrl("valid.zip") });
  try {
    const css = await fetch(`${app.url}/theme-custom.css?v=1`);
    assert.match(css.headers.get("content-type"), /^text\/css/);
    assert.equal(css.headers.get("cache-control"), "no-cache");
    assert.equal(await css.text(), "body { color: red; }");
    assert.equal((await (await fetch(`${app.url}/theme-catalog.json`)).json()).themes[0].id, "paris");
    assert.equal((await (await fetch(`${app.url}/theme-properties.json`)).json()).siteTitle, "Paris Airport");
    assert.equal(
      (await (await fetch(`${app.url}/theme-translations/fr.json`)).json()).rework.home.greeting,
      "Bienvenue",
    );
    const font = await fetch(`${app.url}/images/font.ttf`);
    assert.equal(font.headers.get("content-type"), "font/ttf");
    assert.equal(await font.text(), "font-bytes");
    assert.equal(await (await fetch(`${app.url}/images/logo.svg`)).text(), "<svg>Paris</svg>");
    for (const route of ["/index.html", "/config.json", "/images/missing.png", "/theme-translations/de.json"]) {
      assert.equal(await (await fetch(app.url + route)).text(), "stock");
    }
    const head = await fetch(`${app.url}/theme-custom.css`, { method: "HEAD" });
    assert.equal(await head.text(), "");
    assert.equal(head.headers.get("content-length"), "20");
  } finally {
    await app.close();
  }
});

test("invalid optional archive warns and falls back; required archive refuses startup", async () => {
  const app = await start({ FRONTEND_THEME_URL: archiveUrl("invalid.zip") });
  try {
    assert.equal(await (await fetch(`${app.url}/theme-properties.json`)).text(), "stock");
    assert.match(app.messages.join("\n"), /invalid theme-properties/);
  } finally {
    await app.close();
  }
  await assert.rejects(
    start({ FRONTEND_THEME_URL: archiveUrl("invalid.zip"), FRONTEND_THEME_REQUIRED: "true" }),
    /Theme installation failed/,
  );
  await assert.rejects(
    start({ FRONTEND_THEME_URL: archiveUrl("valid.zip"), FRONTEND_THEME_S3_ACCESS_KEY: "half" }),
    /must be set together/,
  );
});

test("escaping archive is refused and symlink entries are not served", async () => {
  const app = await start({ FRONTEND_THEME_URL: archiveUrl("escaping.zip") });
  try {
    assert.equal(await (await fetch(`${app.url}/theme-custom.css`)).text(), "stock");
  } finally {
    await app.close();
  }
  const links = await start({ FRONTEND_THEME_URL: archiveUrl("symlink.zip") });
  try {
    assert.equal(await (await fetch(`${links.url}/images/leak.svg`)).text(), "stock");
  } finally {
    await links.close();
  }
});

test("blank catalog labels follow the optional fallback and required refusal", async () => {
  const app = await start({ FRONTEND_THEME_URL: archiveUrl("blank-label.zip") });
  try {
    assert.equal(await (await fetch(`${app.url}/theme-catalog.json`)).text(), "stock");
    assert.match(app.messages.join("\n"), /invalid theme-catalog/);
  } finally {
    await app.close();
  }
  await assert.rejects(
    start({ FRONTEND_THEME_URL: archiveUrl("blank-label.zip"), FRONTEND_THEME_REQUIRED: "true" }),
    /invalid theme-catalog/,
  );
});

test("missing optional ZIP falls back and required ZIP refuses startup", async () => {
  const app = await start({ FRONTEND_THEME_URL: archiveUrl("missing.zip") });
  try {
    assert.equal(await (await fetch(`${app.url}/theme-custom.css`)).text(), "stock");
  } finally {
    await app.close();
  }
  await assert.rejects(
    start({ FRONTEND_THEME_URL: archiveUrl("missing.zip"), FRONTEND_THEME_REQUIRED: "true" }),
    /cannot download/,
  );
});

test("middleware rejects encoded traversal and malformed paths before reading files", async () => {
  const directory = await mkdtemp(path.join(fixtures, "overlay-"));
  const middleware = themeOverlayMiddleware(directory);
  for (const url of ["/images/%2e%2e/%2e%2e/secret", "/images/%5csecret", "/images/%00secret", "/images/%GG"]) {
    let fallthrough = false;
    middleware({ method: "GET", url }, { setHeader: () => assert.fail("unexpected read") }, () => {
      fallthrough = true;
    });
    assert.equal(fallthrough, true, url);
  }
});

test("private HTTP ZIP uses SigV4 without logging credentials or signed URL query", async () => {
  let authorization;
  const store = http.createServer(async (req, res) => {
    authorization = req.headers.authorization;
    res.end(await readFile(path.join(fixtures, "valid.zip")));
  });
  store.listen(0, "127.0.0.1");
  await once(store, "listening");
  let app;
  try {
    app = await start({
      FRONTEND_THEME_URL: `http://127.0.0.1:${store.address().port}/theme.zip?token=private-token`,
      FRONTEND_THEME_S3_ACCESS_KEY: "fixture-access-key",
      FRONTEND_THEME_S3_SECRET_KEY: "fixture-secret-key",
    });
    assert.match(authorization, /^AWS4-HMAC-SHA256 /);
    assert.match(authorization, /fixture-access-key/);
    assert.doesNotMatch(app.messages.join("\n"), /fixture-access-key|fixture-secret-key|private-token/);
    assert.equal(await (await fetch(`${app.url}/images/logo.svg`)).text(), "<svg>Paris</svg>");
  } finally {
    if (app) await app.close();
    store.close();
    await once(store, "close");
  }
});

test("startup cleans its temporary overlay and a later unconfigured run serves stock", async () => {
  const before = new Set(await readdir(tmpdir()));
  const app = await start({ FRONTEND_THEME_URL: archiveUrl("valid.zip") });
  const created = (await readdir(tmpdir())).filter((p) => p.startsWith("fred-vite-theme-") && !before.has(p));
  assert.equal(created.length, 1);
  await app.close();
  // Removal is asynchronous after the HTTP server closes.
  for (let i = 0; i < 50 && (await readdir(tmpdir())).includes(created[0]); i++) {
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
  assert.equal((await readdir(tmpdir())).includes(created[0]), false);
  const stock = await start({});
  try {
    assert.equal(await (await fetch(`${stock.url}/theme-custom.css`)).text(), "stock");
  } finally {
    await stock.close();
  }
});

test("replacing the ZIP leaves the running overlay unchanged until startup runs again", async () => {
  const zip = path.join(fixtures, "replacement.zip");
  await copyFile(path.join(fixtures, "valid.zip"), zip);
  const environment = { FRONTEND_THEME_URL: pathToFileURL(zip).href };
  const original = await start(environment);
  let replacement;
  try {
    execFileSync("python3", [
      "-c",
      "import zipfile,sys; z=zipfile.ZipFile(sys.argv[1],'w'); z.writestr('theme-custom.css','replacement CSS'); z.close()",
      zip,
    ]);
    assert.equal(await (await fetch(`${original.url}/theme-custom.css`)).text(), "body { color: red; }");
    replacement = await start(environment);
    assert.equal(await (await fetch(`${replacement.url}/theme-custom.css`)).text(), "replacement CSS");
  } finally {
    await original.close();
    if (replacement) await replacement.close();
  }
});

test("Make lets Vite parse quoted dotenv values and preserves explicit shell overrides", async () => {
  const envFile = path.join(fixtures, ".env");
  await writeFile(
    envFile,
    'FRONTEND_THEME_URL="file:///from-config.zip"\nFRONTEND_THEME_S3_SECRET_KEY="a\\$special"\n',
  );
  const frontend = fileURLToPath(new URL("../", import.meta.url));
  const script = `import { loadEnv } from "vite"; const env = {...loadEnv("development", ${JSON.stringify(fixtures)}, "FRONTEND_THEME_"), ...process.env}; console.log(JSON.stringify({url:env.FRONTEND_THEME_URL, secret:env.FRONTEND_THEME_S3_SECRET_KEY}));`;
  const args = [
    "-s",
    "--no-print-directory",
    "-C",
    frontend,
    `FRONTEND_ENV_FILE=${envFile}`,
    "--eval",
    `print-theme: ; @node --input-type=module -e '${script.replaceAll("$", "$$")}'`,
    "print-theme",
  ];
  const environment = { ...process.env };
  delete environment.FRONTEND_THEME_URL;
  delete environment.FRONTEND_THEME_S3_SECRET_KEY;
  assert.deepEqual(JSON.parse(execFileSync("make", args, { env: environment, encoding: "utf8" })), {
    url: "file:///from-config.zip",
    secret: "a$special",
  });
  environment.FRONTEND_THEME_URL = "file:///from-shell.zip";
  environment.FRONTEND_THEME_S3_SECRET_KEY = "shell$special";
  assert.deepEqual(JSON.parse(execFileSync("make", args, { env: environment, encoding: "utf8" })), {
    url: "file:///from-shell.zip",
    secret: "shell$special",
  });
});

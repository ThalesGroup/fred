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

import { readFileSync } from "node:fs";

const ID_PATTERN = /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/;
const REVISION_PATTERN = /^sha256:[a-f0-9]{64}$/;
const FORBIDDEN_UPSTREAM_CHARACTERS = /[\s$;{}"'\\]/;
const UPSTREAM_PATH_TRAVERSAL_PATTERN = /(?:^|\/)\.{1,2}(?:\/|$)/;
const SAFE_UPSTREAM_PATTERN =
  /^https?:\/\/(?:[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?|\[[0-9A-Fa-f:]+\])(?::(?:[0-9]{1,4}|[1-5][0-9]{4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5]))?(?:\/[A-Za-z0-9._~!&()*+,=:@/-]*)?$/;

function fail(message) {
  throw new Error(`Invalid application service configuration: ${message}`);
}

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function parseJson(raw, source) {
  try {
    return JSON.parse(raw);
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    fail(`${source} is not valid JSON: ${detail}`);
  }
}

function loadRuntimeContract(contractPath) {
  let raw;
  try {
    raw = readFileSync(contractPath, "utf8");
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    fail(`cannot read runtime contract ${contractPath}: ${detail}`);
  }
  const contract = parseJson(raw, contractPath);
  if (
    !isObject(contract) ||
    contract.schema_version !== "1" ||
    typeof contract.catalog_revision !== "string" ||
    !REVISION_PATTERN.test(contract.catalog_revision) ||
    !Array.isArray(contract.applications)
  ) {
    fail(`${contractPath} does not match runtime contract version 1`);
  }

  const applications = [];
  const ids = new Set();
  for (const application of contract.applications) {
    if (
      !isObject(application) ||
      Object.keys(application).sort().join(",") !== "id,service_required" ||
      typeof application.id !== "string" ||
      !ID_PATTERN.test(application.id) ||
      typeof application.service_required !== "boolean"
    ) {
      fail(`${contractPath} contains an invalid application entry`);
    }
    if (ids.has(application.id)) {
      fail(`${contractPath} contains duplicate application id ${JSON.stringify(application.id)}`);
    }
    ids.add(application.id);
    applications.push(application);
  }
  return applications;
}

function normalizeUpstream(value, applicationId) {
  if (typeof value !== "string" || value.length === 0 || FORBIDDEN_UPSTREAM_CHARACTERS.test(value)) {
    fail(`upstream for ${JSON.stringify(applicationId)} must be a safe HTTP(S) URL`);
  }

  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    fail(`upstream for ${JSON.stringify(applicationId)} must be a safe HTTP(S) URL`);
  }
  if (
    !["http:", "https:"].includes(parsed.protocol) ||
    parsed.username !== "" ||
    parsed.password !== "" ||
    parsed.search !== "" ||
    parsed.hash !== "" ||
    parsed.hostname === ""
  ) {
    fail(`upstream for ${JSON.stringify(applicationId)} must be a safe HTTP(S) URL without credentials or query`);
  }
  if (!SAFE_UPSTREAM_PATTERN.test(value) || UPSTREAM_PATH_TRAVERSAL_PATTERN.test(value)) {
    fail(`upstream for ${JSON.stringify(applicationId)} must be a safe HTTP(S) URL`);
  }

  let decodedPath;
  try {
    decodedPath = decodeURIComponent(parsed.pathname);
  } catch {
    fail(`upstream for ${JSON.stringify(applicationId)} contains invalid path encoding`);
  }
  if (decodedPath.split("/").some((segment) => segment === "." || segment === "..")) {
    fail(`upstream for ${JSON.stringify(applicationId)} must not contain path traversal`);
  }

  const normalizedPath = parsed.pathname.replace(/\/+$/, "");
  return `${parsed.origin}${normalizedPath}`;
}

function parseMappings(mappingsJson, installedIds) {
  const parsed = parseJson(mappingsJson || "{}", "FRONTEND_APPLICATION_UPSTREAMS_JSON");
  if (!isObject(parsed)) {
    fail("FRONTEND_APPLICATION_UPSTREAMS_JSON must be an object keyed by installed application id");
  }

  const mappings = new Map();
  for (const applicationId of Object.keys(parsed).sort()) {
    if (!installedIds.has(applicationId)) {
      fail(`upstream mapping references uninstalled application ${JSON.stringify(applicationId)}`);
    }
    mappings.set(applicationId, normalizeUpstream(parsed[applicationId], applicationId));
  }
  return mappings;
}

export function rewriteApplicationServicePath(requestPath, applicationId) {
  const prefix = `/app-services/${applicationId}`;
  if (!requestPath.startsWith(`${prefix}/`)) {
    fail(`request path does not belong to application ${JSON.stringify(applicationId)}`);
  }
  return requestPath.slice(prefix.length);
}

export function parseApplicationServicesEnabled(rawValue) {
  const value = rawValue || "false";
  if (value === "true") return true;
  if (value === "false") return false;
  fail("FRONTEND_ENABLE_APPLICATIONS must be either true or false");
}

export function loadApplicationServiceProxyConfig({
  contractPath,
  mappingsJson = "{}",
  requireRequiredMappings = true,
  enabled = false,
}) {
  if (typeof enabled !== "boolean") {
    fail("enabled must be a boolean");
  }
  if (!enabled) {
    return {
      proxy: {},
      classifyRequest(requestUrl) {
        const path = requestUrl.split("?", 1)[0];
        return path === "/app-services" || path.startsWith("/app-services/") ? 404 : null;
      },
    };
  }

  const applications = loadRuntimeContract(contractPath);
  const installedIds = new Set(applications.map(({ id }) => id));
  const mappings = parseMappings(mappingsJson, installedIds);

  if (requireRequiredMappings) {
    for (const application of applications) {
      if (application.service_required && !mappings.has(application.id)) {
        fail(`service_required application ${JSON.stringify(application.id)} has no upstream mapping`);
      }
    }
  }

  const proxy = {};
  for (const [applicationId, target] of mappings) {
    proxy[`/app-services/${applicationId}`] = {
      target,
      changeOrigin: true,
      secure: true,
      rewrite: (requestPath) => rewriteApplicationServicePath(requestPath, applicationId),
    };
  }

  function classifyRequest(requestUrl) {
    const path = requestUrl.split("?", 1)[0];
    if (path !== "/app-services" && !path.startsWith("/app-services/")) {
      return null;
    }
    for (const applicationId of installedIds) {
      const prefix = `/app-services/${applicationId}`;
      if (path.startsWith(`${prefix}/`)) {
        return mappings.has(applicationId) ? "proxy" : 503;
      }
    }
    return 404;
  }

  return { proxy, classifyRequest };
}

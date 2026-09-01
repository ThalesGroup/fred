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

const ID_PATTERN = /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/;
const FORBIDDEN_UPSTREAM_CHARACTERS = /[\s$;{}"'\\]/;
const UPSTREAM_PATH_TRAVERSAL_PATTERN = /(?:^|\/)\.{1,2}(?:\/|$)/;
const SAFE_UPSTREAM_PATTERN =
  /^https?:\/\/(?:[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?|\[[0-9A-Fa-f:]+\])(?::(?:[0-9]{1,4}|[1-5][0-9]{4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5]))?(?:\/[A-Za-z0-9._~!&()*+,=:@/-]*)?$/;

export const APPLICATION_UI_PREFIX = "/apps";
export const APPLICATION_SERVICE_PREFIX = "/app-services";

const REGISTRATION_KEYS = new Set(["app_id", "ui_upstream", "service_upstream", "service_required"]);

function fail(message) {
  throw new Error(`Invalid application configuration: ${message}`);
}

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function normalizeUpstream(value, applicationId, field) {
  const label = `${field} for ${JSON.stringify(applicationId)}`;
  if (typeof value !== "string" || value.length === 0 || FORBIDDEN_UPSTREAM_CHARACTERS.test(value)) {
    fail(`${label} must be a safe HTTP(S) URL`);
  }

  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    fail(`${label} must be a safe HTTP(S) URL`);
  }
  if (
    !["http:", "https:"].includes(parsed.protocol) ||
    parsed.username !== "" ||
    parsed.password !== "" ||
    parsed.search !== "" ||
    parsed.hash !== "" ||
    parsed.hostname === ""
  ) {
    fail(`${label} must be a safe HTTP(S) URL without credentials or query`);
  }
  if (!SAFE_UPSTREAM_PATTERN.test(value) || UPSTREAM_PATH_TRAVERSAL_PATTERN.test(value)) {
    fail(`${label} must be a safe HTTP(S) URL`);
  }

  let decodedPath;
  try {
    decodedPath = decodeURIComponent(parsed.pathname);
  } catch {
    fail(`${label} contains invalid path encoding`);
  }
  if (decodedPath.split("/").some((segment) => segment === "." || segment === "..")) {
    fail(`${label} must not contain path traversal`);
  }

  const normalizedPath = parsed.pathname.replace(/\/+$/, "");
  return `${parsed.origin}${normalizedPath}`;
}

/**
 * Parse the deployment-owned application registration list.
 *
 * Registration is deployment configuration, not a build artifact: a fork
 * builds and ships its own UI and service images, and names them here.
 */
export function parseApplicationRegistrations(registrationsJson) {
  const source = "FRONTEND_APPLICATIONS_JSON";
  let parsed;
  try {
    parsed = JSON.parse(registrationsJson || "[]");
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    fail(`${source} is not valid JSON: ${detail}`);
  }
  if (!Array.isArray(parsed)) {
    fail(`${source} must be an array of application registrations`);
  }

  const registrations = [];
  const ids = new Set();
  for (const entry of parsed) {
    if (!isObject(entry) || Object.keys(entry).some((key) => !REGISTRATION_KEYS.has(key))) {
      fail(`${source} contains an entry with unsupported keys`);
    }
    if (typeof entry.app_id !== "string" || !ID_PATTERN.test(entry.app_id)) {
      fail(`${source} contains an entry without a valid app_id`);
    }
    if (ids.has(entry.app_id)) {
      fail(`${source} contains duplicate app_id ${JSON.stringify(entry.app_id)}`);
    }
    const serviceRequired = entry.service_required ?? false;
    if (typeof serviceRequired !== "boolean") {
      fail(`service_required for ${JSON.stringify(entry.app_id)} must be a boolean`);
    }
    const serviceUpstream =
      entry.service_upstream === undefined || entry.service_upstream === null
        ? null
        : normalizeUpstream(entry.service_upstream, entry.app_id, "service_upstream");
    ids.add(entry.app_id);
    registrations.push({
      app_id: entry.app_id,
      ui_upstream: normalizeUpstream(entry.ui_upstream, entry.app_id, "ui_upstream"),
      service_upstream: serviceUpstream,
      service_required: serviceRequired,
    });
  }
  return registrations;
}

/**
 * The UI bundle keeps its own `/apps/<id>` prefix upstream so the absolute
 * asset URLs baked into it by the fork's build keep resolving through here.
 */
export function rewriteApplicationUiPath(requestPath, applicationId) {
  const prefix = `${APPLICATION_UI_PREFIX}/${applicationId}`;
  const [path] = requestPath.split("?", 1);
  if (path !== prefix && !path.startsWith(`${prefix}/`)) {
    fail(`request path does not belong to application ${JSON.stringify(applicationId)}`);
  }
  return requestPath;
}

export function rewriteApplicationServicePath(requestPath, applicationId) {
  const prefix = `${APPLICATION_SERVICE_PREFIX}/${applicationId}`;
  if (!requestPath.startsWith(`${prefix}/`)) {
    fail(`request path does not belong to application ${JSON.stringify(applicationId)}`);
  }
  return requestPath.slice(prefix.length);
}

export function parseApplicationsEnabled(rawValue) {
  const value = rawValue || "false";
  if (value === "true") return true;
  if (value === "false") return false;
  fail("FRONTEND_ENABLE_APPLICATIONS must be either true or false");
}

export function loadApplicationProxyConfig({
  registrationsJson = "[]",
  requireServiceUpstreams = true,
  enabled = false,
}) {
  if (typeof enabled !== "boolean") {
    fail("enabled must be a boolean");
  }
  if (!enabled) {
    // Fail closed without parsing: a disabled deployment must not need valid
    // application configuration to start.
    return {
      proxy: {},
      classifyRequest(requestUrl) {
        const [path] = requestUrl.split("?", 1);
        for (const namespace of [APPLICATION_UI_PREFIX, APPLICATION_SERVICE_PREFIX]) {
          if (path === namespace || path.startsWith(`${namespace}/`)) return 404;
        }
        return null;
      },
    };
  }

  const registrations = parseApplicationRegistrations(registrationsJson);
  if (requireServiceUpstreams) {
    for (const registration of registrations) {
      if (registration.service_required && registration.service_upstream === null) {
        fail(`service_required application ${JSON.stringify(registration.app_id)} has no service_upstream`);
      }
    }
  }

  const proxy = {};
  for (const registration of registrations) {
    proxy[`${APPLICATION_UI_PREFIX}/${registration.app_id}`] = {
      target: registration.ui_upstream,
      changeOrigin: true,
      secure: true,
      rewrite: (requestPath) => rewriteApplicationUiPath(requestPath, registration.app_id),
    };
    if (registration.service_upstream !== null) {
      proxy[`${APPLICATION_SERVICE_PREFIX}/${registration.app_id}`] = {
        target: registration.service_upstream,
        changeOrigin: true,
        secure: true,
        rewrite: (requestPath) => rewriteApplicationServicePath(requestPath, registration.app_id),
      };
    }
  }

  function classifyRequest(requestUrl) {
    const [path] = requestUrl.split("?", 1);
    if (path === APPLICATION_UI_PREFIX || path.startsWith(`${APPLICATION_UI_PREFIX}/`)) {
      for (const registration of registrations) {
        const prefix = `${APPLICATION_UI_PREFIX}/${registration.app_id}`;
        if (path === prefix || path.startsWith(`${prefix}/`)) return "proxy";
      }
      return 404;
    }
    if (path === APPLICATION_SERVICE_PREFIX || path.startsWith(`${APPLICATION_SERVICE_PREFIX}/`)) {
      for (const registration of registrations) {
        const prefix = `${APPLICATION_SERVICE_PREFIX}/${registration.app_id}`;
        if (path.startsWith(`${prefix}/`)) return registration.service_upstream === null ? 503 : "proxy";
      }
      return 404;
    }
    return null;
  }

  return { proxy, classifyRequest };
}

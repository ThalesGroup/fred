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

import type { PatchUserPreferences, UserPreferences } from "../slices/controlPlane/controlPlaneOpenApi";

const PREFIX = "fred.usersPreferences:";
const IMPORTED_KEY = "fred.usersPreferences.legacyImported";
const LEGACY_OWNER_KEY = "fred.usersPreferences.legacyImportOwner";
const PENDING_LEGACY_PREFIX = "fred.usersPreferences.pendingLegacy:";
const THEME_KEY = "localHook:ApplicationContextProvider.uiTheme";
const MODE_KEY = "localHook:ApplicationContextProvider.themeMode";
const SIDEBAR_KEY = "localHook:ApplicationContextProvider.isSidebarCollapsed";
const TRACE_KEY = "localHook:chatTraceExpanded";
const TEAM_SORT_KEY = "fred.teamSortMode";
const AGENT_SORT_KEY = "fred.agentSort";
const LANGUAGE_KEY = "i18nextLng";
let activeUserId: string | null = null;
let pendingSave: Promise<unknown> = Promise.resolve();
let preferenceStore: (typeof import("../common/store"))["store"] | null = null;
let preferenceApi: (typeof import("../slices/controlPlane/controlPlaneOpenApi"))["controlPlaneApi"] | null = null;

function get(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function set(key: string, value: string | null): void {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    // Browser storage is optional; the server remains authoritative.
  }
}

function parsed(key: string): unknown {
  const raw = get(key);
  if (raw === null) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function readLegacyPreferences(): PatchUserPreferences {
  const patch: PatchUserPreferences = {};
  const theme = parsed(THEME_KEY);
  if (typeof theme === "string" && /^[a-z][a-z0-9-]{0,31}$/.test(theme)) patch.ui_theme_id = theme;
  const mode = parsed(MODE_KEY);
  if (mode === "light" || mode === "dark" || mode === "system") patch.theme_mode = mode;
  const sidebar = parsed(SIDEBAR_KEY);
  if (typeof sidebar === "boolean") patch.sidebar_collapsed = sidebar;
  const trace = parsed(TRACE_KEY);
  if (typeof trace === "boolean") patch.trace_expanded = trace;
  const language = get(LANGUAGE_KEY)?.slice(0, 2);
  if (language === "fr" || language === "en") patch.language = language;
  const teamSort = get(TEAM_SORT_KEY);
  if (teamSort === "recent" || teamSort === "alpha") patch.team_sort_mode = teamSort;
  const agentSort = get(AGENT_SORT_KEY);
  if (agentSort === "name" || agentSort === "created_at:desc" || agentSort === "updated_at:desc") {
    patch.agent_sort = agentSort;
  }
  return patch;
}

function readPendingLegacyPreferences(value: unknown): PatchUserPreferences | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const pending = value as Record<string, unknown>;
  const patch: PatchUserPreferences = {};
  if (typeof pending.ui_theme_id === "string" && /^[a-z][a-z0-9-]{0,31}$/.test(pending.ui_theme_id)) {
    patch.ui_theme_id = pending.ui_theme_id;
  }
  if (pending.theme_mode === "light" || pending.theme_mode === "dark" || pending.theme_mode === "system") {
    patch.theme_mode = pending.theme_mode;
  }
  if (pending.language === "fr" || pending.language === "en") patch.language = pending.language;
  if (typeof pending.sidebar_collapsed === "boolean") patch.sidebar_collapsed = pending.sidebar_collapsed;
  if (pending.team_sort_mode === "recent" || pending.team_sort_mode === "alpha") {
    patch.team_sort_mode = pending.team_sort_mode;
  }
  if (
    pending.agent_sort === "name" ||
    pending.agent_sort === "created_at:desc" ||
    pending.agent_sort === "updated_at:desc"
  ) {
    patch.agent_sort = pending.agent_sort;
  }
  if (typeof pending.trace_expanded === "boolean") patch.trace_expanded = pending.trace_expanded;
  return patch;
}

function cacheKey(userId: string): string {
  return PREFIX + encodeURIComponent(userId);
}

function readCache(userId: string): UserPreferences | null {
  try {
    const raw = get(cacheKey(userId));
    return raw ? (JSON.parse(raw) as UserPreferences) : null;
  } catch {
    return null;
  }
}

async function writeLocalChoices(preferences: UserPreferences): Promise<void> {
  set(THEME_KEY, JSON.stringify(preferences.ui_theme_id ?? null));
  set(MODE_KEY, JSON.stringify(preferences.theme_mode ?? "system"));
  set(SIDEBAR_KEY, JSON.stringify(preferences.sidebar_collapsed ?? false));
  set(TRACE_KEY, JSON.stringify(preferences.trace_expanded ?? null));
  set(TEAM_SORT_KEY, preferences.team_sort_mode ?? "recent");
  set(AGENT_SORT_KEY, preferences.agent_sort ?? "name");
  const { default: i18n } = await import("../i18n");
  if (preferences.language) await i18n.changeLanguage(preferences.language);
  else await i18n.changeLanguage(navigator.language?.startsWith("fr") ? "fr" : "en");
}

export async function initializeUserPreferences(userId: string): Promise<void> {
  const [{ store }, { controlPlaneApi }] = await Promise.all([
    import("../common/store"),
    import("../slices/controlPlane/controlPlaneOpenApi"),
  ]);
  preferenceStore = store;
  preferenceApi = controlPlaneApi;
  activeUserId = userId;
  const pendingKey = PENDING_LEGACY_PREFIX + encodeURIComponent(userId);
  const owner = get(LEGACY_OWNER_KEY);
  const canImport = get(IMPORTED_KEY) !== "1" && (!owner || owner === userId);
  let legacy: PatchUserPreferences = {};
  if (canImport) {
    if (!owner) set(LEGACY_OWNER_KEY, userId);
    try {
      const pending: unknown = JSON.parse(get(pendingKey) ?? "null");
      const saved = readPendingLegacyPreferences(pending);
      legacy = saved && Object.keys(saved).length ? saved : readLegacyPreferences();
    } catch {
      legacy = readLegacyPreferences();
    }
    if (Object.keys(legacy).length) set(pendingKey, JSON.stringify(legacy));
  }
  const request = store.dispatch(
    controlPlaneApi.endpoints.getMyPreferencesControlPlaneV1UsersMePreferencesGet.initiate(undefined, {
      forceRefetch: true,
    }),
  );
  try {
    let preferences = await request.unwrap();
    if (!preferences.initialized && canImport) {
      if (Object.keys(legacy).length) {
        const write = store.dispatch(
          controlPlaneApi.endpoints.patchMyPreferencesControlPlaneV1UsersMePreferencesPatch.initiate({
            patchUserPreferences: legacy,
          }),
        );
        try {
          preferences = await write.unwrap();
          set(IMPORTED_KEY, "1");
        } finally {
          write.reset();
        }
      }
    }
    if (canImport) {
      set(IMPORTED_KEY, "1");
      set(LEGACY_OWNER_KEY, null);
      set(pendingKey, null);
    }
    set(cacheKey(userId), JSON.stringify(preferences));
    await writeLocalChoices(preferences);
  } catch {
    await writeLocalChoices(readCache(userId) ?? {});
  } finally {
    request.unsubscribe();
  }
}

export async function saveUserPreference(patch: PatchUserPreferences): Promise<void> {
  if (!activeUserId) return;
  const userId = activeUserId;
  const save = pendingSave.then(async () => {
    if (activeUserId !== userId) return;
    const store = preferenceStore;
    const controlPlaneApi = preferenceApi;
    if (!store || !controlPlaneApi) return;
    const request = store.dispatch(
      controlPlaneApi.endpoints.patchMyPreferencesControlPlaneV1UsersMePreferencesPatch.initiate({
        patchUserPreferences: patch,
      }),
    );
    try {
      const preferences = await request.unwrap();
      set(cacheKey(userId), JSON.stringify(preferences));
    } finally {
      request.reset();
    }
  });
  pendingSave = save.catch(() => undefined);
  await save;
}

export function persistUserPreference(patch: PatchUserPreferences): void {
  void saveUserPreference(patch).catch(() => {
    // Local controls remain usable until the server is reachable again.
  });
}

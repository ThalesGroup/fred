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
import { useSyncExternalStore } from "react";

// Failed writes use a separate, account-scoped session fallback; old browser keys are ignored.
let currentPreferences: UserPreferences = {};
const listeners = new Set<() => void>();
let activeUserId: string | null = null;
let pendingSave: Promise<unknown> = Promise.resolve();
let preferenceStore: (typeof import("../common/store"))["store"] | null = null;
let preferenceApi: (typeof import("../slices/controlPlane/controlPlaneOpenApi"))["controlPlaneApi"] | null = null;
const sessionFallbackPrefix = "fred.userPreferencesFallback:";
const preferenceFields = [
  "ui_theme_id",
  "theme_mode",
  "language",
  "sidebar_collapsed",
  "team_sort_mode",
  "agent_sort",
  "resources_tree_open",
] as const satisfies readonly (keyof UserPreferences)[];

function sessionFallbackKey(userId: string): string {
  return `${sessionFallbackPrefix}${encodeURIComponent(userId)}`;
}

function readSessionFallback(userId: string): PatchUserPreferences {
  try {
    const parsed: unknown = JSON.parse(sessionStorage.getItem(sessionFallbackKey(userId)) ?? "null");
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    const fallback: Record<string, unknown> = {};
    for (const key of preferenceFields) {
      if (Object.prototype.hasOwnProperty.call(parsed, key)) fallback[key] = (parsed as Record<string, unknown>)[key];
    }
    return fallback as PatchUserPreferences;
  } catch {
    return {};
  }
}

function updateSessionFallback(userId: string, patch: PatchUserPreferences, clear: boolean): void {
  try {
    const next: Record<string, unknown> = { ...readSessionFallback(userId) };
    for (const key of preferenceFields) {
      if (!Object.prototype.hasOwnProperty.call(patch, key)) continue;
      if (clear || patch[key] === undefined) delete next[key];
      else next[key] = patch[key];
    }
    const storageKey = sessionFallbackKey(userId);
    if (Object.keys(next).length) sessionStorage.setItem(storageKey, JSON.stringify(next));
    else sessionStorage.removeItem(storageKey);
  } catch {
    // The in-memory choice remains usable if browser storage is unavailable.
  }
}

export function getCurrentUserPreferences(): UserPreferences {
  return currentPreferences;
}

export function setCurrentUserPreferences(preferences: UserPreferences): void {
  currentPreferences = preferences;
  listeners.forEach((listener) => listener());
}

export function updateCurrentUserPreference(patch: PatchUserPreferences): void {
  setCurrentUserPreferences({ ...currentPreferences, ...patch });
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useCurrentUserPreference<K extends keyof UserPreferences, T extends UserPreferences[K]>(
  key: K,
  fallback: T,
): Exclude<UserPreferences[K], undefined> | T {
  return useSyncExternalStore(
    subscribe,
    () => currentPreferences[key] ?? fallback,
    () => fallback,
  ) as Exclude<UserPreferences[K], undefined> | T;
}

async function applyPreferences(preferences: UserPreferences): Promise<void> {
  setCurrentUserPreferences(preferences);
  const { default: i18n } = await import("../i18n");
  if (preferences.language) await i18n.changeLanguage(preferences.language);
  else await i18n.changeLanguage(navigator.language?.startsWith("fr") ? "fr" : "en");
}

export async function initializeUserPreferences(userId: string | null): Promise<UserPreferences> {
  if (activeUserId !== userId) pendingSave = Promise.resolve();
  activeUserId = userId;
  if (!userId) {
    const defaults: UserPreferences = {};
    await applyPreferences(defaults);
    return defaults;
  }
  const [{ store }, { controlPlaneApi }] = await Promise.all([
    import("../common/store"),
    import("../slices/controlPlane/controlPlaneOpenApi"),
  ]);
  preferenceStore = store;
  preferenceApi = controlPlaneApi;
  const request = store.dispatch(
    controlPlaneApi.endpoints.getMyPreferencesControlPlaneV1UsersMePreferencesGet.initiate(undefined, {
      forceRefetch: true,
    }),
  );
  try {
    const preferences = await request.unwrap();
    if (activeUserId !== userId) return currentPreferences;
    const resolved = { ...preferences, ...readSessionFallback(userId) };
    await applyPreferences(resolved);
    return resolved;
  } catch {
    if (activeUserId !== userId) return currentPreferences;
    const fallback = readSessionFallback(userId);
    await applyPreferences(fallback);
    return fallback;
  } finally {
    request.unsubscribe();
  }
}

function isTransientPreferenceError(error: unknown): boolean {
  const status = (error as { status?: number | string })?.status;
  return status === "FETCH_ERROR" || status === "TIMEOUT_ERROR" || (typeof status === "number" && status >= 500);
}

export async function saveUserPreference(patch: PatchUserPreferences, retryTransient = false): Promise<void> {
  if (!activeUserId) return;
  const userId = activeUserId;
  const save = pendingSave.then(async () => {
    if (activeUserId !== userId) return;
    const store = preferenceStore;
    const controlPlaneApi = preferenceApi;
    if (!store || !controlPlaneApi) return;
    for (let attempt = 0; attempt < (retryTransient ? 2 : 1); attempt++) {
      if (activeUserId !== userId) return;
      const request = store.dispatch(
        controlPlaneApi.endpoints.patchMyPreferencesControlPlaneV1UsersMePreferencesPatch.initiate({
          patchUserPreferences: patch,
        }),
      );
      try {
        await request.unwrap();
        if (activeUserId === userId) updateSessionFallback(userId, patch, true);
        return;
      } catch (error) {
        if (attempt === 0 && retryTransient && isTransientPreferenceError(error)) continue;
        if (activeUserId === userId) updateSessionFallback(userId, patch, false);
        return;
      } finally {
        request.reset();
      }
    }
  });
  pendingSave = save.catch(() => undefined);
  await save;
}

export function persistUserPreference(patch: PatchUserPreferences): void {
  updateCurrentUserPreference(patch);
  void saveUserPreference(patch, true).catch((error) => console.error("Could not save user preferences", error));
}

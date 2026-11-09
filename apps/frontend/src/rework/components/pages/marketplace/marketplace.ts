// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import type { TFunction } from "i18next";
import { normalizeApiError } from "@core/errors/normalizeApiError";
import { KeyCloakService } from "../../../../security/KeycloakService";
import type {
  InstallationReceipt,
  InstallMarketplaceEntryApiArg,
  SubmitMarketplaceProposalApiArg,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";

type MarketplaceRequest =
  | Omit<SubmitMarketplaceProposalApiArg, "Idempotency-Key">
  | Omit<InstallMarketplaceEntryApiArg, "Idempotency-Key">;
export type AttemptContext = { name: string; destination: string; startedAt?: string };
type SavedAttempt<Args> = { args: Args; key: string; context?: AttemptContext };
type AttemptState<Args, Result> = {
  storageKey: string;
  attempt?: SavedAttempt<Args>;
  busy?: boolean;
  result?: Result;
  error?: unknown;
};
function rejectedRequest(error: unknown) {
  const { status, code } = normalizeApiError(error);
  // A refusal to read a replay is not proof of failure of the original command.
  return status !== undefined && [400, 409, 422].includes(status) && code !== "idempotency_conflict";
}
const storageError = { code: "attempt_storage_unavailable" };

function restoreAttempt<Args, Result>(storageKey: string): AttemptState<Args, Result> {
  try {
    const raw = sessionStorage.getItem(storageKey);
    if (!raw) return { storageKey };
    const saved = JSON.parse(raw);
    if (!saved || typeof saved.key !== "string" || !saved.args || typeof saved.args.marketplaceSpaceId !== "string")
      throw new Error("Invalid saved attempt");
    return { storageKey, attempt: { args: saved.args, key: saved.key, context: saved.context } };
  } catch {
    // Never silently replace an unreadable, potentially accepted attempt.
    return { storageKey, error: storageError };
  }
}

/** Guard retained callbacks and late completions, including after a context unmount. */
export function useMarketplaceSession() {
  const actor = KeyCloakService.GetSessionIdentity();
  const mounted = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  return () => mounted.current && !!actor && actor === KeyCloakService.GetSessionIdentity();
}

/** Discover existing requests only; this is neither a result cache nor an access check. */
export function savedProposalRequests(marketplaceSpaceId: string, kind: string) {
  const requests: SavedAttempt<Omit<SubmitMarketplaceProposalApiArg, "Idempotency-Key">>[] = [];
  try {
    const actor = KeyCloakService.GetSessionIdentity();
    for (let index = 0; index < sessionStorage.length; index++) {
      const key = sessionStorage.key(index)!;
      if (!key.startsWith("marketplace.attempt.v1:")) continue;
      const scope = JSON.parse(key.slice("marketplace.attempt.v1:".length));
      if (scope[0] !== actor || scope[1] !== "proposal" || scope[3] !== kind) continue;
      const saved = restoreAttempt<Omit<SubmitMarketplaceProposalApiArg, "Idempotency-Key">, never>(key);
      const args = saved.attempt?.args;
      if (args?.marketplaceSpaceId === marketplaceSpaceId && args.submitProposalRequest?.kind === kind)
        requests.push(saved.attempt!);
    }
  } catch {
    /* Storage may be unavailable; opening a new attempt reports that failure. */
  }
  return requests;
}

/** Persist only unresolved commands. Acknowledged success removes recovery, never caches permissions. */
export function useMarketplaceAttempt<Args extends MarketplaceRequest, Result>(scope: string[]) {
  const sessionActive = useMarketplaceSession();
  const actor = KeyCloakService.GetSessionIdentity();
  const storageKey = `marketplace.attempt.v1:${JSON.stringify([actor, ...scope])}`;
  const [state, setState] = useState(() => restoreAttempt<Args, Result>(storageKey));
  const current = useRef(state);
  if (current.current.storageKey !== storageKey) {
    current.current = restoreAttempt<Args, Result>(storageKey);
    setState(current.current);
  }
  const active = () => sessionActive() && current.current.storageKey === storageKey;
  const update = (next: AttemptState<Args, Result>) => {
    current.current = next;
    setState(next);
  };
  const run = async (args: Args, send: (args: Args, key: string) => Promise<Result>, context?: AttemptContext) => {
    if (!active() || current.current.busy || current.current.result || current.current.error === storageError) return;
    const attempt = current.current.attempt ?? {
      args,
      key: crypto.randomUUID(),
      context: context && { ...context, startedAt: new Date().toISOString() },
    };
    // Synchronous write BEFORE dispatch: failure means nothing is sent.
    try {
      sessionStorage.setItem(storageKey, JSON.stringify(attempt));
    } catch {
      update({ ...current.current, error: storageError });
      return;
    }
    update({ storageKey, attempt, busy: true });
    try {
      const result = await send(attempt.args, attempt.key);
      // Cleanup also applies after unmount: the response acknowledges this exact persisted key.
      // Do not erase a newer command or publish an old account's result into the current UI.
      try {
        if (JSON.parse(sessionStorage.getItem(storageKey) ?? "null")?.key === attempt.key)
          sessionStorage.removeItem(storageKey);
      } catch {
        /* Keep the original request for safe server reconciliation if storage failed. */
      }
      if (active() && current.current.attempt === attempt) update({ storageKey, attempt, result });
    } catch (error) {
      if (rejectedRequest(error)) {
        try {
          if (JSON.parse(sessionStorage.getItem(storageKey) ?? "null")?.key === attempt.key)
            sessionStorage.removeItem(storageKey);
        } catch {
          /* Preserve recovery if storage is unavailable. */
        }
      }
      if (active() && current.current.attempt === attempt) update({ storageKey, attempt, error });
    }
  };
  // A restored request is unresolved until an explicit retry asks the server.
  const canReset = !state.busy && (!!state.result || rejectedRequest(state.error));
  const reset = () => {
    if (!active() || !canReset) return;
    try {
      sessionStorage.removeItem(storageKey);
      update({ storageKey });
    } catch {
      update({ ...current.current, error: storageError });
    }
  };
  return {
    run,
    reset,
    canReset,
    busy: state.busy,
    error: state.error,
    result: state.result,
    started: !!state.attempt,
    args: state.attempt?.args,
    context: state.attempt?.context,
  };
}

export function marketplaceError(error: unknown, t: TFunction, destination?: string, command = false) {
  if ((error as { code?: string } | null)?.code === "attempt_storage_unavailable")
    return t("rework.localMarketplace.attemptStorageUnavailable");
  const normalized = normalizeApiError(error);
  if (normalized.status === 401 || normalized.status === 403) return t("rework.localMarketplace.forbidden");
  if (destination && ["conflict", "name_conflict"].includes(normalized.code ?? ""))
    return t("rework.localMarketplace.nameConflict", { destination });
  if (normalized.code === "publication_changed") return t("rework.localMarketplace.reviewAgain");
  if (normalized.code === "source_changed") return t("rework.localMarketplace.sourceChanged");
  const key =
    normalized.status === undefined || normalized.status >= 500 ? (command ? "uncertain" : "loadFailed") : "failed";
  return `${t(`rework.localMarketplace.${key}`)}${normalized.detail && normalized.status ? ` ${normalized.detail}` : ""}`;
}

export function installationPath(receipt: InstallationReceipt) {
  const page = { prompt: "prompts", skill: "skills", agent: "agents" }[receipt.kind];
  return `/team/${encodeURIComponent(receipt.space_id)}/${page}?resource=${encodeURIComponent(receipt.resource_id)}`;
}

/** Personal-space storage names may be owner UUIDs; they are not user-facing names. */
export function marketplaceName(name: string, t: TFunction) {
  return /^[0-9a-f]{8}-[0-9a-f-]{27}$/i.test(name) ? t("rework.home.topTeams.personalSpace") : name;
}

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
type AttemptState<Args, Result> = {
  storageKey: string;
  attempt?: { args: Args; key: string };
  busy?: boolean;
  result?: Result;
  error?: unknown;
};
const storageError = { code: "attempt_storage_unavailable" };

function restoreAttempt<Args, Result>(storageKey: string): AttemptState<Args, Result> {
  try {
    const raw = sessionStorage.getItem(storageKey);
    if (!raw) return { storageKey };
    const saved = JSON.parse(raw);
    if (!saved || typeof saved.key !== "string" || !saved.args || typeof saved.args.marketplaceSpaceId !== "string")
      throw new Error("Invalid saved attempt");
    return { storageKey, attempt: { args: saved.args, key: saved.key } };
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
  const requests: Omit<SubmitMarketplaceProposalApiArg, "Idempotency-Key">[] = [];
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
        requests.push(args);
    }
  } catch {
    /* Storage may be unavailable; opening a new attempt reports that failure. */
  }
  return requests;
}

/** Only the request and its key survive reloads; results and permissions always come from the server. */
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
  const run = async (args: Args, send: (args: Args, key: string) => Promise<Result>) => {
    if (!active() || current.current.busy || current.current.result || current.current.error === storageError) return;
    const attempt = current.current.attempt ?? { args, key: crypto.randomUUID() };
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
      if (active() && current.current.attempt === attempt) update({ storageKey, attempt, result });
    } catch (error) {
      if (active() && current.current.attempt === attempt) update({ storageKey, attempt, error });
    }
  };
  const status = normalizeApiError(state.error).status;
  // A restored request is unresolved until an explicit retry asks the server.
  const canReset = !state.busy && (!!state.result || (status !== undefined && status >= 400 && status < 500));
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
  };
}

export function marketplaceError(error: unknown, t: TFunction) {
  if ((error as { code?: string } | null)?.code === "attempt_storage_unavailable")
    return t("rework.localMarketplace.attemptStorageUnavailable");
  const normalized = normalizeApiError(error);
  const key =
    normalized.code === "publication_changed"
      ? "reviewAgain"
      : normalized.code === "source_changed"
        ? "sourceChanged"
        : normalized.status === undefined || normalized.status >= 500
          ? "uncertain"
          : "failed";
  return `${t(`rework.localMarketplace.${key}`)}${normalized.detail && normalized.status ? ` ${normalized.detail}` : ""}`;
}

export function installationPath(receipt: InstallationReceipt) {
  const page = { prompt: "prompts", skill: "skills", agent: "agents" }[receipt.kind];
  return `/team/${encodeURIComponent(receipt.space_id)}/${page}?resource=${encodeURIComponent(receipt.resource_id)}`;
}

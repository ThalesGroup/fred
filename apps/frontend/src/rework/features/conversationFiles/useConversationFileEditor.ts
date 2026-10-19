// Copyright Thales 2026
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy at http://www.apache.org/licenses/LICENSE-2.0

import { useCallback, useEffect, useRef, useState } from "react";
import { useLazyReadConversationFileQuery } from "../../../slices/runtime/runtimeOpenApi";
import { type ConversationEditors, useConversationFileDraft } from "./conversationEditors";

/** Shared source/Markdown/HTML lifecycle: only a clean, unchanged buffer accepts a read. */
export function useConversationFileEditor(
  coordinator: ConversationEditors,
  sessionId: string,
  teamId: string,
  path: string,
  refreshRevision: number,
) {
  const identity = { sessionId, teamId, path };
  const draft = useConversationFileDraft(coordinator, identity);
  const [read] = useLazyReadConversationFileQuery();
  const request = useRef<ReturnType<typeof read> | null>(null);
  const generation = useRef(0);
  const refreshQueued = useRef(false);
  const mounted = useRef(false);
  const [error, setError] = useState<unknown>();
  const [loading, setLoading] = useState(true);
  const refresh = useCallback((): void => {
    const before = coordinator.get({ sessionId, teamId, path });
    if (before && (before.saving || before.content !== before.savedContent)) return;
    if (request.current) {
      refreshQueued.current = true;
      return;
    }
    const current = ++generation.current;
    const pending = read({ sessionId, teamId, path }, false);
    request.current = pending;
    void pending
      .unwrap()
      .then((file) => {
        if (!mounted.current || current !== generation.current) return;
        const latest = coordinator.get({ sessionId, teamId, path });
        if (latest?.version === before?.version && !latest?.saving)
          coordinator.accept({ sessionId, teamId, path }, file);
        setError(undefined);
      })
      .catch((failure: unknown) => {
        if (mounted.current && current === generation.current) setError(failure);
      })
      .finally(() => {
        if (mounted.current && current === generation.current) {
          request.current = null;
          setLoading(false);
          if (refreshQueued.current) {
            refreshQueued.current = false;
            refresh();
          }
        }
      });
  }, [coordinator, read, sessionId, teamId, path]);
  useEffect(() => {
    mounted.current = true;
    const visibleRefresh = () => {
      if (document.visibilityState !== "hidden") refresh();
    };
    const timer = setInterval(visibleRefresh, 5000);
    window.addEventListener("focus", visibleRefresh);
    document.addEventListener("visibilitychange", visibleRefresh);
    return () => {
      mounted.current = false;
      generation.current += 1;
      request.current?.abort();
      request.current = null;
      refreshQueued.current = false;
      clearInterval(timer);
      window.removeEventListener("focus", visibleRefresh);
      document.removeEventListener("visibilitychange", visibleRefresh);
    };
  }, [refresh]);
  useEffect(() => {
    refresh();
  }, [refresh, refreshRevision, draft?.saveRevision ?? 0]);
  return {
    draft,
    error,
    loading,
    refresh,
    change: (content: string) => coordinator.change(identity, content),
    flush: () => coordinator.flushFile(identity),
  };
}

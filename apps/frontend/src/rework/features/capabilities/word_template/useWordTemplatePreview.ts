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

// The word_template pane's data: the session state (generated hook, polled)
// and the PDF preview bytes (raw fetch, see sessionDocument.ts).
//
// How the pane learns about edits: word_template emits no chat part - it is
// an operation log on the backend. Every tool call that changes the document
// records one batch, which bumps the session's `edit_count`/`updated_at`. So
// the session route is polled (cheap JSON read) and the preview is re-fetched
// only when that version key changes - one conversion per agent edit, none
// while idle.

import { useCallback, useEffect, useRef, useState } from "react";
import { useCapabilityRouted } from "../useCapabilityRouted";
import { useOpenSessionId } from "../useOpenSessionId";
import { CAPABILITY_ID } from "./api/wordTemplateCapabilityApi";
import { useGetWordTemplateSessionQuery } from "./api/wordTemplateCapabilityOpenApi";
import {
  attachedBaseFilename,
  fetchSessionBinary,
  previewVersionKey,
  type WordTemplateFetchError,
} from "./sessionDocument";

/** Session-state poll period while the pane or the panel launcher is mounted. */
export const SESSION_POLL_MS = 4000;

export function useWordTemplateSession(sessionId: string) {
  return useGetWordTemplateSessionQuery(
    { sessionId },
    {
      skip: !sessionId,
      pollingInterval: SESSION_POLL_MS,
      skipPollingIfUnfocused: true,
      refetchOnMountOrArgChange: true,
    },
  );
}

/**
 * Launcher visibility for the side panel (`CapabilitySidePanelSpec.useHasContent`):
 * the OPEN conversation holds a Word document. Same polled query as the pane
 * (RTK Query dedupes it), so the launcher lights up once the agent writes the
 * first edit - there is no chat part to announce it. `currentData`, not `data`:
 * a stale answer from the previous conversation must not light this one.
 */
export function useHasWordTemplateDocument(): boolean {
  const sessionId = useOpenSessionId();
  const routed = useCapabilityRouted(CAPABILITY_ID);
  const { currentData: session } = useGetWordTemplateSessionQuery(
    { sessionId },
    { skip: !sessionId || !routed, pollingInterval: SESSION_POLL_MS, skipPollingIfUnfocused: true },
  );
  return previewVersionKey(session) !== null;
}

export interface UseWordTemplatePreviewResult {
  /** Blob object URL of the PDF, or null while loading / on error / no document. */
  objectUrl: string | null;
  isLoading: boolean;
  error: WordTemplateFetchError | null;
  /** The version key the current preview was fetched for (null = no document). */
  version: string | null;
  /** The attached file's name when the document is built on one (else null). */
  attachedFilename: string | null;
  /** Re-read the session state now (after a collaborator edit): a new version re-renders the preview. */
  refresh: () => void;
}

export function useWordTemplatePreview(baseUrl: string | undefined, sessionId: string): UseWordTemplatePreviewResult {
  // `currentData`: the previous conversation's answer must not show here.
  const { currentData: session, refetch } = useWordTemplateSession(sessionId);
  const version = previewVersionKey(session);

  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<WordTemplateFetchError | null>(null);
  const createdRef = useRef<string | null>(null);

  // Another conversation: its PDF is not this one's.
  useEffect(() => setObjectUrl(null), [sessionId]);

  useEffect(() => {
    if (!baseUrl || !sessionId || version === null) {
      setObjectUrl(null);
      setError(null);
      setIsLoading(false);
      return;
    }
    // Aborting on cleanup cancels a superseded request (StrictMode drill, or a
    // newer edit) before it pays for the LibreOffice conversion.
    const controller = new AbortController();
    setIsLoading(true);
    setError(null);
    void (async () => {
      try {
        const blob = await fetchSessionBinary({ baseUrl, sessionId, file: "preview.pdf", signal: controller.signal });
        if (createdRef.current) URL.revokeObjectURL(createdRef.current);
        const created = URL.createObjectURL(blob);
        createdRef.current = created;
        setObjectUrl(created);
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") return;
        const { status, detail } = err instanceof Error ? (err as Error & { status?: number; detail?: string }) : {};
        setError({ message: err instanceof Error ? err.message : String(err), status, detail });
        setObjectUrl(null);
      } finally {
        if (!controller.signal.aborted) setIsLoading(false);
      }
    })();
    return () => controller.abort();
  }, [baseUrl, sessionId, version]);

  useEffect(() => {
    return () => {
      if (createdRef.current) URL.revokeObjectURL(createdRef.current);
    };
  }, []);

  const refresh = useCallback(() => {
    if (sessionId) void refetch();
  }, [sessionId, refetch]);

  return { objectUrl, isLoading, error, version, attachedFilename: attachedBaseFilename(session), refresh };
}

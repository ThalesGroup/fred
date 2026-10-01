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

// usePptxPreview — fetches the preview PDF for the side panel (mirrors
// ppt_filler's usePptPreview). react-pdf can't attach an Authorization
// header itself, so this hook fetches the bearer-protected bytes and hands
// it a blob object URL instead of the raw `pdf_download_url`.

import { useCallback, useEffect, useState } from "react";
import { KeyCloakService } from "../../../../security/KeycloakService";
import type { PptxGeneratedPartData } from "./types";

export interface UsePptxPreviewResult {
  /** Blob object URL for the fetched PDF, or null while loading / on error. */
  objectUrl: string | null;
  isLoading: boolean;
  /** Error message, or null. */
  error: string | null;
  /** Force a re-fetch of the current preview (same preview_id + version). */
  refetch: () => void;
}

/** Append the version as a cache-bust query param, preserving any existing query. */
function withVersion(url: string, version: string): string {
  const sep = url.includes("?") ? "&" : "?";
  return `${url}${sep}v=${encodeURIComponent(version)}`;
}

export function usePptxPreview(preview: PptxGeneratedPartData | null): UsePptxPreviewResult {
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadNonce, setReloadNonce] = useState(0);

  const refetch = useCallback(() => setReloadNonce((n) => n + 1), []);

  const downloadUrl = preview?.pdf_download_url;
  const version = preview?.version;

  useEffect(() => {
    if (!downloadUrl || version === undefined) {
      setObjectUrl(null);
      setError(null);
      setIsLoading(false);
      return;
    }

    let cancelled = false;
    let created: string | null = null;
    // The previous run's cleanup revoked its URL; keeping it in state would hand
    // react-pdf a dead blob for the length of the re-fetch.
    setObjectUrl(null);
    setIsLoading(true);
    setError(null);

    void (async () => {
      try {
        const res = await fetch(withVersion(downloadUrl, version), {
          headers: { Authorization: `Bearer ${KeyCloakService.GetToken() ?? ""}` },
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const blob = await res.blob();
        if (cancelled) return;
        created = URL.createObjectURL(blob);
        setObjectUrl(created);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    })();

    return () => {
      cancelled = true;
      // Revoke the URL this run created so blobs don't leak across regenerations.
      if (created) URL.revokeObjectURL(created);
    };
  }, [downloadUrl, version, reloadNonce]);

  return { objectUrl, isLoading, error, refetch };
}

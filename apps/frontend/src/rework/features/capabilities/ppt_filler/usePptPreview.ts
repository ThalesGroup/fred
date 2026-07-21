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

// usePptPreview
// -------------
// Fetches the preview PDF for the side panel. The `ppt_preview` part carries a
// durable, bearer-protected KF `/fs/download` href (`pdf_download_url`); react-pdf
// cannot attach an Authorization header itself, so this hook fetches the bytes WITH
// the live bearer (same token source as `downloadAuthed`) and hands react-pdf a
// blob object URL instead of the raw href.
//
// Freshness: `version` is appended as a `?v=` cache-bust and is part of the refetch
// key, so a re-fill (new version) re-fetches instead of showing a browser-cached
// stale deck. The object URL is revoked on cleanup so blobs never leak.
//
// Key scoping: the returned `objectUrl` is tagged with the deck key it was
// fetched for and returned ONLY while that key is current. Without this, the
// render right after a deck switch would briefly expose the PREVIOUS deck's URL
// under the NEW remount key, mounting a `<Document>` that immediately unmounts —
// the exact extra mount/unmount cycle that races pdf.js worker teardown
// ("PDFWorker.fromPort - the worker is being destroyed").

import { useCallback, useEffect, useState } from "react";
import { KeyCloakService } from "../../../../security/KeycloakService";
import type { PptPreviewPartData } from "./types";

export interface UsePptPreviewResult {
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

export function usePptPreview(preview: PptPreviewPartData | null): UsePptPreviewResult {
  const [fetched, setFetched] = useState<{ key: string; url: string } | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadNonce, setReloadNonce] = useState(0);

  const refetch = useCallback(() => setReloadNonce((n) => n + 1), []);

  const downloadUrl = preview?.pdf_download_url;
  const version = preview?.version;
  const key = preview ? `${preview.preview_id}:${preview.version}` : null;

  useEffect(() => {
    if (!downloadUrl || !key || version === undefined) {
      setFetched(null);
      setError(null);
      setIsLoading(false);
      return;
    }

    let cancelled = false;
    let created: string | null = null;
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
        setFetched({ key, url: created });
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    })();

    return () => {
      cancelled = true;
      // Revoke the URL this run created so blobs don't leak across re-fills.
      if (created) URL.revokeObjectURL(created);
    };
  }, [downloadUrl, key, version, reloadNonce]);

  // Only expose a URL fetched for the CURRENT deck key (see header comment).
  const objectUrl = fetched && fetched.key === key ? fetched.url : null;

  return { objectUrl, isLoading, error, refetch };
}

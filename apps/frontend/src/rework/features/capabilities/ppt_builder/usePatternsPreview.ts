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

// The patterns PDF (one page per inventory pattern) behind the review
// thumbnails, as a blob URL. Three sources, one hook: the staged file goes
// through the capability's stateless `/preview` route, a saved template is
// read from the Knowledge Flow path stored in the config, and the built-in
// theme from the capability's `/theme/preview.pdf`. Binary responses are the
// sanctioned raw-fetch exception; the bearer travels the same way as for the
// chat preview.

import { useEffect, useState } from "react";
import { useSelector } from "react-redux";
import { KeyCloakService } from "../../../../security/KeycloakService";
import { fetchAuthedBlob } from "../../../../utils/downloadUtils";
import { selectCapabilityBaseUrl, type CapabilityRoutingState } from "../../../../common/capabilityRoutingSlice";
import { CAPABILITY_ID } from "./api/pptBuilderCapabilityApi";

export type PreviewSource =
  | { kind: "staged"; file: File }
  | { kind: "persisted"; path: string }
  | { kind: "theme" }
  | null;

export interface PatternsPreview {
  objectUrl: string | null;
  isLoading: boolean;
  error: string | null;
}

async function fetchStagedPreview(baseUrl: string, file: File): Promise<Blob> {
  const formData = new FormData();
  formData.append("file", file, file.name);
  const response = await fetch(`${baseUrl}/preview`, {
    method: "POST",
    headers: { Authorization: `Bearer ${KeyCloakService.GetToken() ?? ""}` },
    body: formData,
  });
  if (!response.ok) throw new Error(`Preview failed (${response.status})`);
  return response.blob();
}

export function usePatternsPreview(source: PreviewSource): PatternsPreview {
  const baseUrl = useSelector((state: { capabilityRouting: CapabilityRoutingState }) =>
    selectCapabilityBaseUrl(state, CAPABILITY_ID),
  );
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Identity of the request, so a re-pick of the same File object is a no-op
  // and a source change always refetches.
  const key = source
    ? source.kind === "staged"
      ? `staged:${source.file.name}:${source.file.size}:${source.file.lastModified}`
      : source.kind === "persisted"
        ? `persisted:${source.path}`
        : "theme"
    : "none";
  // The capability routes need the pod's base URL; the KF path does not.
  const needsRouting = source !== null && source.kind !== "persisted";

  useEffect(() => {
    if (!source || (needsRouting && !baseUrl)) {
      setObjectUrl(null);
      setError(null);
      setIsLoading(false);
      return;
    }
    let cancelled = false;
    let created: string | null = null;
    setObjectUrl(null);
    setError(null);
    setIsLoading(true);
    void (async () => {
      try {
        let blob: Blob;
        if (source.kind === "staged") {
          blob = await fetchStagedPreview(baseUrl as string, source.file);
        } else if (source.kind === "persisted") {
          blob = await fetchAuthedBlob(`/knowledge-flow/v1/fs/download/${encodeURI(source.path)}`);
        } else {
          blob = await fetchAuthedBlob(`${baseUrl}/theme/preview.pdf`);
        }
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
      if (created) URL.revokeObjectURL(created);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, baseUrl]);

  return { objectUrl, isLoading, error };
}

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
// thumbnails, as a blob URL: the agent's analysed template or the built-in
// one. Binary responses are the sanctioned raw-fetch exception.

import { useEffect, useState } from "react";
import { useSelector } from "react-redux";
import { fetchAuthedBlob } from "../../../../utils/downloadUtils";
import { selectCapabilityBaseUrl, type CapabilityRoutingState } from "../../../../common/capabilityRoutingSlice";
import { CAPABILITY_ID } from "./api/pptBuilderCapabilityApi";

export type PreviewSource = { kind: "analysis"; instanceId: string } | { kind: "builtin" } | null;

export interface PatternsPreview {
  objectUrl: string | null;
  isLoading: boolean;
  error: string | null;
}

export function usePatternsPreview(source: PreviewSource): PatternsPreview {
  const baseUrl = useSelector((state: { capabilityRouting: CapabilityRoutingState }) =>
    selectCapabilityBaseUrl(state, CAPABILITY_ID),
  );
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const path = !source
    ? null
    : source.kind === "analysis"
      ? `/analysis/${encodeURIComponent(source.instanceId)}/patterns.pdf`
      : "/builtin/patterns.pdf";

  useEffect(() => {
    if (!path || !baseUrl) {
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
        const blob = await fetchAuthedBlob(`${baseUrl}${path}`);
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
  }, [path, baseUrl]);

  return { objectUrl, isLoading, error };
}

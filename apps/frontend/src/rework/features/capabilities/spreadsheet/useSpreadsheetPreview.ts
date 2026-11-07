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

// The spreadsheet the OPEN conversation registered, and the JSON preview behind
// it. The preview lives behind the bearer-protected `/fs/download` route, so it is
// fetched with the live token (as ppt_filler fetches its PDF).

import { useEffect, useState } from "react";
import { useSelector } from "react-redux";
import { fetchAuthedBlob } from "../../../../utils/downloadUtils";
import { useOpenSessionId } from "../useOpenSessionId";
import { selectSpreadsheetPreview } from "./spreadsheetPreviewSlice";
import type { SpreadsheetPreview, SpreadsheetPreviewPartData } from "./types";

export function useSessionSpreadsheet(): SpreadsheetPreviewPartData | null {
  const sessionId = useOpenSessionId();
  const { sessionId: owner, current } = useSelector(selectSpreadsheetPreview);
  return sessionId !== "" && owner === sessionId ? current : null;
}

/** Launcher visibility for the spreadsheet side panel - see `CapabilitySidePanelSpec`. */
export function useHasSpreadsheet(): boolean {
  return useSessionSpreadsheet() !== null;
}

export type SpreadsheetPreviewLoad =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; preview: SpreadsheetPreview };

function isPreview(value: unknown): value is SpreadsheetPreview {
  return Array.isArray((value as SpreadsheetPreview | null)?.sheets);
}

export function useSpreadsheetPreview(url: string | undefined): SpreadsheetPreviewLoad {
  // Tagged with its url, so a switch to another file never shows the previous one.
  const [load, setLoad] = useState<{ url: string; result: SpreadsheetPreviewLoad } | null>(null);

  useEffect(() => {
    if (!url) return;
    let cancelled = false;
    const settle = (result: SpreadsheetPreviewLoad) => {
      if (!cancelled) setLoad({ url, result });
    };
    void (async () => {
      try {
        const parsed: unknown = JSON.parse(await (await fetchAuthedBlob(url)).text());
        settle(isPreview(parsed) ? { status: "ready", preview: parsed } : { status: "error" });
      } catch {
        settle({ status: "error" });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [url]);

  return load && load.url === url ? load.result : { status: "loading" };
}

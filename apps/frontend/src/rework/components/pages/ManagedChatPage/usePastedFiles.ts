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

import { useEffect, useRef } from "react";
import { clipboardAttachments } from "@core/utils/clipboardFiles";

interface UsePastedFilesParams {
  enabled: boolean;
  onFiles: (files: File[]) => void;
}

/**
 * Routes a file paste anywhere on the page to the attachments, the way drop
 * already covers the whole page. Listening on the composer alone missed every
 * Ctrl+V made while the focus sat elsewhere - a paste event only reaches the
 * focused element and its ancestors, so the document is the one place that
 * sees them all. A text paste is left alone.
 */
export function usePastedFiles({ enabled, onFiles }: UsePastedFilesParams) {
  const onFilesRef = useRef(onFiles);
  onFilesRef.current = onFiles;

  useEffect(() => {
    if (!enabled) return;
    const handlePaste = (event: ClipboardEvent) => {
      const files = clipboardAttachments(event.clipboardData);
      // What the browser exposed vs. what was kept: browsers and file managers
      // differ on how many files one copy yields, so this is the first thing
      // to check when "I pasted N files and see fewer".
      console.debug(
        `[usePastedFiles] paste — types=${Array.from(event.clipboardData?.types ?? []).join(",")} files=${event.clipboardData?.files.length ?? 0} attached=${files.length}`,
      );
      if (files.length === 0) return;
      event.preventDefault();
      onFilesRef.current(files);
    };
    document.addEventListener("paste", handlePaste);
    return () => document.removeEventListener("paste", handlePaste);
  }, [enabled]);
}

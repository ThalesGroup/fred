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

import { useEffect, useMemo, useRef, useState } from "react";
import { composeHtmlDocument } from "./htmlArtifactDocument";
import { nextBufferAction } from "./previewBuffers";
import styles from "./HtmlPreview.module.css";

/** Static, opaque-origin preview shared by live files and legacy HTML artifacts. */
export function HtmlPreview({
  html,
  css = "",
  zoom = 1,
  title,
}: {
  html: string;
  css?: string;
  zoom?: number;
  title: string;
}) {
  const composed = useMemo(() => composeHtmlDocument(html, css, zoom), [html, css, zoom]);
  // Keep the painted frame visible while the other sandboxed frame loads.
  // Zoom requires a reload, so stable buffers avoid a blank preview flash.
  const [buffers, setBuffers] = useState<[string, string]>(["", ""]);
  const [front, setFront] = useState<0 | 1>(0);
  // An unchanged srcdoc does not reload; remember painted documents to reuse them.
  const paintedRef = useRef<[string, string]>(["", ""]);
  // Hide both buffers until the first document has painted.
  const [revealed, setRevealed] = useState(false);

  useEffect(() => {
    const action = nextBufferAction(composed, buffers, paintedRef.current, front);
    if (action.kind === "flip") {
      setFront(action.to);
      setRevealed(true);
    } else if (action.kind === "load") {
      // A reloading buffer cannot be reused until the requested document paints.
      paintedRef.current[action.into] = "";
      setBuffers((b) => {
        const next: [string, string] = [b[0], b[1]];
        next[action.into] = composed;
        return next;
      });
    }
  }, [composed, front, buffers]);

  const handleFrameLoad = (idx: 0 | 1) => {
    paintedRef.current[idx] = buffers[idx];
    // A fast switch may have replaced the target while this frame was loading.
    if (buffers[idx] === composed && front !== idx) {
      setFront(idx);
      setRevealed(true);
    }
  };

  return (
    <div className={styles.previewFrameWrap}>
      {([0, 1] as const).map((i) => (
        <iframe
          key={i}
          // No attribute while empty: in Chromium, a doc set while the empty srcdoc is
          // still loading paints blank.
          srcDoc={buffers[i] || undefined}
          className={`${styles.previewFrame} ${revealed && front === i ? styles.frameFront : styles.frameBack}`}
          title={title}
          tabIndex={revealed && front === i ? 0 : -1}
          aria-hidden={!revealed || front !== i}
          sandbox=""
          referrerPolicy="no-referrer"
          onLoad={() => handleFrameLoad(i)}
        />
      ))}
    </div>
  );
}

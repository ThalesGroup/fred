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
  // Double-buffer the Preview so a zoom / markup change never flashes the iframe's
  // blank white background: the newly composed document loads into the HIDDEN back
  // buffer and is revealed only once it has painted (onLoad); the front buffer keeps
  // the previous frame visible until then. Each iframe keeps a STABLE key, so only
  // the back one ever reloads — an iframe cannot be re-zoomed without a reload
  // (sandboxed, no allow-scripts), so this hides that reload instead of avoiding it.
  const [buffers, setBuffers] = useState<[string, string]>(["", ""]);
  const [front, setFront] = useState<0 | 1>(0);
  // What each buffer has actually painted. Switching back to an already-seen
  // document doesn't reload the iframe (same srcDoc), so no onLoad fires — we must
  // recognise "already painted here" and flip to it directly, or the pane freezes.
  const paintedRef = useRef<[string, string]>(["", ""]);
  // On the very first open there is no prior frame to hold, so the empty front
  // iframe would flash its white background before the artifact paints. Keep both
  // frames hidden (the pane's own surface shows through) until that first paint.
  const [revealed, setRevealed] = useState(false);

  useEffect(() => {
    const action = nextBufferAction(composed, buffers, paintedRef.current, front);
    if (action.kind === "flip") {
      setFront(action.to);
      setRevealed(true);
    } else if (action.kind === "load") {
      // This buffer is about to reload, so its previously-painted content is void:
      // clear it now, or a quick switch back to that old doc would flip to this
      // buffer mid-load (showing the new doc) instead of reloading the old one.
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
    // Reveal the freshly loaded buffer only once the doc we asked it to load has
    // painted AND it is still the current target (a fast switch may have moved on).
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

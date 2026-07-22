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

// Local shape of the `ppt_preview` chat part emitted by the ppt_filler runtime.
//
// The backend `UiPart` union is OPEN (capability packages extend it at pod boot),
// so this build carries a hand-written narrowing type instead of a generated one —
// the same pattern DemoCardPartRenderer uses for `DemoCardPart`. Renderers narrow
// the `RawUiPart` they receive to this via `as unknown as PptPreviewPartData`.

/** One filled-deck PDF preview reference, as carried on a `ppt_preview` part. */
export interface PptPreviewPartData {
  type: "ppt_preview";
  /** Stable id of the deck being previewed (one per filled document). */
  preview_id: string;
  /** Human title shown on the card and the pane header. */
  title: string;
  /**
   * Durable, origin-relative Knowledge Flow `/fs/download` href for the rendered
   * PDF. It is bearer-protected — fetch it WITH the Authorization header (never a
   * bare anchor). Stays valid across chat reloads (no expiring signature baked in).
   */
  pdf_download_url: string;
  /**
   * Per-fill content hash. Doubles as the PDF cache-bust query value and the
   * react-pdf remount key, so a re-fill re-fetches instead of showing a stale deck.
   */
  version: string;
  /** Bearer-protected KF href for the source `.pptx` (download button). */
  pptx_download_url?: string;
  /** Suggested download file name for the `.pptx`. */
  file_name?: string;
}

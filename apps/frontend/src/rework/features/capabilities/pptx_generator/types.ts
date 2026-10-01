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

// Local shape of the `pptx_generated` chat part emitted by the pptx_generator
// runtime (PPTX-GENERATOR-CAPABILITY-RFC.md §4.4).
//
// The backend `UiPart` union is OPEN (capability packages extend it at pod boot),
// so this build carries a hand-written narrowing type instead of a generated one —
// the same pattern PptPreviewPartData / HtmlArtifactPartData use. Renderers narrow
// the RAW part they receive via `as unknown as PptxGeneratedPartData`.
//
// Deliberately NOT PptPreviewPartData: a distinct backend class/discriminator
// (`PptxGeneratedPart` / "pptx_generated") avoids a chat-part registry collision
// between the two independent PPTX capabilities (RFC §4.4) — kept distinct here too.

/** Backend capability id (`manifest.id`) — the side-panel open-request key. */
export const CAPABILITY_ID = "pptx_generator";

/** One generated deck's PDF preview reference, as carried on a `pptx_generated` part. */
export interface PptxGeneratedPartData {
  type: "pptx_generated";
  /** Stable id of the deck being previewed (one per generated document). */
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
   * Per-generation content hash (sha256(pdf_bytes)[:16]). Doubles as the PDF
   * cache-bust query value and the react-pdf remount key, so a regeneration
   * re-fetches instead of showing a stale deck.
   */
  version: string;
  /** Bearer-protected KF href for the source `.pptx`, or null if PDF conversion
   *  failed and the tool fell back to a plain download link outside this part. */
  pptx_download_url: string | null;
  /** Suggested download file name for the `.pptx`, or null. */
  file_name: string | null;
}

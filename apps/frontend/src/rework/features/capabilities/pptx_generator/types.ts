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

// Hand-written narrowing type for the `pptx_generated` chat part: the backend
// `UiPart` union is open (extended at pod boot), so none is generated. Distinct
// from PptPreviewPartData to avoid a registry collision with ppt_filler.

/** Backend capability id (`manifest.id`) — the side-panel open-request key. */
export const CAPABILITY_ID = "pptx_generator";

/** One generated deck's PDF preview reference, as carried on a `pptx_generated` part. */
export interface PptxGeneratedPartData {
  type: "pptx_generated";
  /** Stable id of the deck being previewed (one per generated document). */
  preview_id: string;
  /** Human title shown on the card and the pane header. */
  title: string;
  /** Bearer-protected, origin-relative KF `/fs/download` href for the PDF; fetch it
   *  with the Authorization header. Stays valid across chat reloads. */
  pdf_download_url: string;
  /** Per-generation content hash: PDF cache-bust value and react-pdf remount key,
   *  so a regeneration re-fetches instead of showing a stale deck. */
  version: string;
  /** Bearer-protected KF href for the source `.pptx`, or null if PDF conversion
   *  failed and the tool fell back to a plain download link outside this part. */
  pptx_download_url: string | null;
  /** Suggested download file name for the `.pptx`, or null. */
  file_name: string | null;
}

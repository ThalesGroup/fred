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

// Local shape of the `writable_document` chat part emitted by the writable_document
// runtime middleware (the `write_document` tool artifact).
//
// The backend `UiPart` union is OPEN (capability packages extend it at pod boot),
// so this build carries a hand-written narrowing type instead of a generated one —
// the same pattern PptPreviewPartData / DemoCardPart use. It is NOT a mirror of a
// router model (those come from the generated client); it narrows the RAW part a
// renderer receives via `as unknown as WritableDocumentPartData`.

/** One collaborative-document snapshot, as carried on a `writable_document` part. */
export interface WritableDocumentPartData {
  type: "writable_document";
  /** Stable id of the document (one per collaborative document in the session). */
  document_id: string;
  /** Human title shown on the card, the tab, and the pane header. */
  title: string;
  /** Full Markdown body (the tool replaces content wholesale, never appends). */
  content_md: string;
  /** ISO timestamp of this write — the freshness key that drives merge + remount. */
  updated_at: string;
  /** Who produced this snapshot: an agent write or a user edit. */
  updated_by: "agent" | "user";
}

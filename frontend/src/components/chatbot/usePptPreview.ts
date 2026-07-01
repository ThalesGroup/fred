// Copyright Thales 2025
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

/**
 * usePptPreview
 * -------------
 * Owns the state for the read-only PPT PDF preview pane:
 * - the set of preview decks that arrived live in the chat stream (latest per preview_id);
 * - the currently selected deck and whether the pane is open.
 *
 * Mirrors `useWritableDocuments` but is read-only: there is no list API, no autosave, and
 * no local optimistic content. The source of truth is the `ppt_preview` message part the
 * fill tool emits. A re-fill carries a new `version`, which downstream drives a fresh PDF
 * fetch + react-pdf remount so the open pane updates live (the edit→preview loop).
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChatMessage, PptPreviewPart } from "../../slices/agentic/agenticOpenApi";

export type PptPreview = {
  preview_id: string;
  title: string;
  pdf_url: string;
  version: string;
  pptx_download_url?: string | null;
  file_name?: string | null;
};

export type UsePptPreview = {
  previews: PptPreview[];
  selectedId: string | null;
  selected: PptPreview | null;
  selectPreview: (previewId: string) => void;
  isPaneOpen: boolean;
  openPane: (previewId?: string) => void;
  closePane: () => void;
};

/** Extract PptPreviewParts from the chat stream, keeping the latest per preview_id. */
function previewsFromMessages(messages: ChatMessage[]): PptPreview[] {
  const ordered = [...messages].sort((a, b) => a.rank - b.rank);
  const byId = new Map<string, PptPreview>();
  for (const msg of ordered) {
    for (const part of msg.parts ?? []) {
      if ((part as { type?: string }).type !== "ppt_preview") continue;
      const p = part as PptPreviewPart;
      // Later messages win (ordered by rank), so a re-fill's newer part with a fresh
      // `version` replaces the earlier one under the same preview_id.
      byId.set(p.preview_id, {
        preview_id: p.preview_id,
        title: p.title,
        pdf_url: p.pdf_url,
        version: p.version,
        pptx_download_url: p.pptx_download_url,
        file_name: p.file_name,
      });
    }
  }
  return [...byId.values()];
}

export function usePptPreview(sessionId: string | undefined, messages: ChatMessage[]): UsePptPreview {
  const previews = useMemo(() => previewsFromMessages(messages), [messages]);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [isPaneOpen, setIsPaneOpen] = useState(false);

  const selectPreview = useCallback((previewId: string) => setSelectedId(previewId), []);

  const openPane = useCallback((previewId?: string) => {
    setIsPaneOpen(true);
    if (previewId) setSelectedId(previewId);
  }, []);

  const closePane = useCallback(() => setIsPaneOpen(false), []);

  // Auto-open the pane (and select the latest deck) the first time a preview appears for
  // this session, so the user sees the filled deck immediately without any click.
  const autoOpenedRef = useRef(false);
  useEffect(() => {
    if (!autoOpenedRef.current && previews.length > 0) {
      autoOpenedRef.current = true;
      setIsPaneOpen(true);
      setSelectedId((prev) => prev ?? previews[previews.length - 1].preview_id);
    }
  }, [previews]);

  // Keep a valid selection when the preview set changes.
  useEffect(() => {
    if (previews.length === 0) {
      setSelectedId(null);
      return;
    }
    setSelectedId((prev) => (prev && previews.some((p) => p.preview_id === prev) ? prev : previews[0].preview_id));
  }, [previews]);

  // Reset when switching sessions.
  useEffect(() => {
    setSelectedId(null);
    setIsPaneOpen(false);
    autoOpenedRef.current = false;
  }, [sessionId]);

  const selected = useMemo(
    () => previews.find((p) => p.preview_id === selectedId) ?? previews[0] ?? null,
    [previews, selectedId],
  );

  return { previews, selectedId, selected, selectPreview, isPaneOpen, openPane, closePane };
}

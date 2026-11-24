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

// Chat images are copied to the Word capability so the agent can place them.
// The editor fetches them with a bearer token because <img> cannot send one.

import { createContext, useContext } from "react";
import { KeyCloakService } from "../../../../security/KeycloakService";
import type { ChatAttachmentContext } from "../types";
import { type WordTemplateImageResponse } from "./api/wordTemplateCapabilityOpenApi";

const ATTACHMENT_UPLOAD_TIMEOUT_MS = 30_000;

/** The bearer header is refreshed because a chat can outlive the token. */
async function freshAuthHeader(): Promise<{ Authorization: string }> {
  await KeyCloakService.ensureFreshToken(30);
  return { Authorization: `Bearer ${KeyCloakService.GetToken() ?? ""}` };
}

/** The formats the Word document can embed (checked again by their bytes server-side). */
const PLACEABLE_IMAGE_TYPES = new Set(["image/png", "image/jpeg", "image/gif"]);
const PLACEABLE_IMAGE_EXTENSION = /\.(png|jpe?g|gif)$/i;
export const IMAGE_REF_PREFIX = "img:";

const imagesUrl = (baseUrl: string, sessionId: string) => `${baseUrl}/sessions/${encodeURIComponent(sessionId)}/images`;

export const isPlaceableImage = (file: File) =>
  PLACEABLE_IMAGE_TYPES.has(file.type) || (!file.type && PLACEABLE_IMAGE_EXTENSION.test(file.name));

/**
 * Keeps an attached PNG/JPEG/GIF for the session. Never rejects - a failed or
 * timed-out upload is logged and the chat attachment goes on as usual.
 */
export async function captureImageAttachment(
  file: File,
  { baseUrl, sessionId, teamId }: ChatAttachmentContext,
): Promise<WordTemplateImageResponse | null> {
  if (!isPlaceableImage(file)) return null;
  try {
    const form = new FormData();
    form.append("file", file, file.name);
    const res = await fetch(`${imagesUrl(baseUrl, sessionId)}?space_id=${encodeURIComponent(teamId)}`, {
      method: "POST",
      headers: await freshAuthHeader(),
      body: form,
      signal: AbortSignal.timeout(ATTACHMENT_UPLOAD_TIMEOUT_MS),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return (await res.json()) as WordTemplateImageResponse;
  } catch (error) {
    console.warn(`[word_template] could not keep the attached image ${file.name}`, error);
    return null;
  }
}

/**
 * Forgets a kept image when the user removes it from the chat. The server
 * keeps it (409) once the document places it; never rejects.
 */
export async function forgetImageAttachment(
  { baseUrl, sessionId, teamId }: ChatAttachmentContext,
  imageId: string,
): Promise<void> {
  try {
    const response = await fetch(
      `${imagesUrl(baseUrl, sessionId)}/${encodeURIComponent(imageId)}?space_id=${encodeURIComponent(teamId)}`,
      {
        method: "DELETE",
        headers: await freshAuthHeader(),
        signal: AbortSignal.timeout(ATTACHMENT_UPLOAD_TIMEOUT_MS),
      },
    );
    if (!response.ok && response.status !== 404 && response.status !== 409) throw new Error(`HTTP ${response.status}`);
  } catch (error) {
    console.warn(`[word_template] could not forget the attached image ${imageId}`, error);
  }
}

/** Turns an image src into something an `<img>` can show. */
export type ImageResolver = (src: string) => Promise<string>;

type PreviewEntry = { pending: Promise<string>; objectUrl?: string };

// Blob URLs survive editor remounts within one conversation.
const previewCache = new Map<string, PreviewEntry>();

/**
 * MDXEditor `imagePreviewHandler` (and the reading view's resolver): turns an
 * `img:<id>` src into a displayable blob URL. Any other src is returned unchanged.
 */
export function resolveImagePreview(baseUrl: string | undefined, sessionId: string | null): ImageResolver {
  return async (src: string): Promise<string> => {
    if (!src.startsWith(IMAGE_REF_PREFIX) || !baseUrl || !sessionId) return src;
    const url = `${imagesUrl(baseUrl, sessionId)}/${encodeURIComponent(src.slice(IMAGE_REF_PREFIX.length))}`;
    let entry = previewCache.get(url);
    if (!entry) {
      entry = { pending: Promise.resolve(src) };
      const current = entry;
      entry.pending = freshAuthHeader()
        .then((headers) => fetch(url, { headers }))
        .then(async (res) => {
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          const objectUrl = URL.createObjectURL(await res.blob());
          if (previewCache.get(url) !== current) {
            URL.revokeObjectURL(objectUrl);
            return src;
          }
          current.objectUrl = objectUrl;
          return objectUrl;
        });
      // A failed fetch must not stay cached forever.
      entry.pending.catch(() => {
        if (previewCache.get(url) === current) previewCache.delete(url);
      });
      previewCache.set(url, entry);
    }
    return entry.pending;
  };
}

/** Forget previews when their conversation closes or changes. */
export function clearImagePreviewCache(): void {
  for (const entry of previewCache.values()) {
    if (entry.objectUrl) URL.revokeObjectURL(entry.objectUrl);
  }
  previewCache.clear();
}

const passThrough: ImageResolver = async (src) => src;

/** The pane provides the session's resolver; the rich-text blocks read it. */
export const WordTemplateImagesContext = createContext<ImageResolver>(passThrough);

export const useImageResolver = () => useContext(WordTemplateImagesContext);

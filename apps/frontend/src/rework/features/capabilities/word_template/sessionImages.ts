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

// Session images for word_template. An image attached in the chat is
// copied to
// `POST /sessions/{id}/images` (the platform keeps no attachment
// bytes); the pictures of an attached .docx are extracted server-side. The
// agent places them as `![caption](img:<id>)`, and the "Rédaction" view
// resolves those references through `GET /sessions/{id}/images/{id}` (an
// `<img>` cannot send the bearer). Raw `fetch` is the sanctioned exception -
// multipart upload and binary read, which the generated client can't
// express; the response TYPE still comes from the generated client.

import { createContext, useContext } from "react";
import type { ChatAttachmentContext } from "../types";
import { wordTemplateCapabilityApi, type WordTemplateImageResponse } from "./api/wordTemplateCapabilityOpenApi";
import { ATTACHMENT_UPLOAD_TIMEOUT_MS, freshAuthHeader, isGone } from "./sessionAttachments";

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
  { baseUrl, sessionId }: ChatAttachmentContext,
): Promise<WordTemplateImageResponse | null> {
  if (!isPlaceableImage(file)) return null;
  try {
    const form = new FormData();
    form.append("file", file, file.name);
    const res = await fetch(imagesUrl(baseUrl, sessionId), {
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
  { dispatch, sessionId }: ChatAttachmentContext,
  imageId: string,
): Promise<void> {
  try {
    await dispatch(
      wordTemplateCapabilityApi.endpoints.deleteWordTemplateImage.initiate({ sessionId, imageId }),
    ).unwrap();
  } catch (error) {
    if (isGone(error)) return;
    console.warn(`[word_template] could not forget the attached image ${imageId}`, error);
  }
}

/** Turns an image src into something an `<img>` can show. */
export type ImageResolver = (src: string) => Promise<string>;

// Blob URLs survive the editor's remounts: each image is fetched once per page load.
const previewCache = new Map<string, Promise<string>>();

/**
 * MDXEditor `imagePreviewHandler` (and the reading view's resolver): turns an
 * `img:<id>` src into a displayable blob URL. Any other src is returned unchanged.
 */
export function resolveImagePreview(baseUrl: string | undefined, sessionId: string | null): ImageResolver {
  return async (src: string): Promise<string> => {
    if (!src.startsWith(IMAGE_REF_PREFIX) || !baseUrl || !sessionId) return src;
    const url = `${imagesUrl(baseUrl, sessionId)}/${encodeURIComponent(src.slice(IMAGE_REF_PREFIX.length))}`;
    let pending = previewCache.get(url);
    if (!pending) {
      pending = freshAuthHeader()
        .then((headers) => fetch(url, { headers }))
        .then(async (res) => {
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          return URL.createObjectURL(await res.blob());
        });
      // A failed fetch must not stay cached forever.
      pending.catch(() => previewCache.delete(url));
      previewCache.set(url, pending);
    }
    return pending;
  };
}

/** Test seam: forget every resolved image. */
export function clearImagePreviewCache(): void {
  previewCache.clear();
}

const passThrough: ImageResolver = async (src) => src;

/** The pane provides the session's resolver; the rich-text blocks read it. */
export const WordTemplateImagesContext = createContext<ImageResolver>(passThrough);

export const useImageResolver = () => useContext(WordTemplateImagesContext);

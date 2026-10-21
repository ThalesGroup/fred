// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

const PREVIEW_BYTES = 8 * 1024 * 1024;

/** Bound raw previews before fetchBaseQuery clones and consumes their bodies. */
export const managerFetch: typeof fetch = async (input, init) => {
  const response = await fetch(input, init);
  const url = new URL(input instanceof Request ? input.url : String(input), window.location.origin);
  if (!url.pathname.endsWith("/preview") || (url.searchParams.get("artifact") ?? "raw") !== "raw") return response;
  const reader = response.body?.getReader();
  if (!reader) return response;
  try {
    if (Number(response.headers.get("content-length")) > PREVIEW_BYTES) throw new Error("preview_too_large");
    const chunks: Uint8Array<ArrayBuffer>[] = [];
    let size = 0;
    while (true) {
      const block = await reader.read();
      if (block.done) break;
      size += block.value.byteLength;
      if (size > PREVIEW_BYTES) throw new Error("preview_too_large");
      chunks.push(new Uint8Array(block.value));
    }
    return new Response(new Blob(chunks), {
      status: response.status,
      statusText: response.statusText,
      headers: response.headers,
    });
  } finally {
    await reader.cancel();
  }
};

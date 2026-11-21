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

// Images: an attached image goes to /images, a .docx still goes to
// /attachments (the
// server extracts its pictures), and `img:` references resolve through the
// image route.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../../security/KeycloakService", () => ({
  KeyCloakService: { GetToken: () => "tok", ensureFreshToken: () => Promise.resolve(true) },
}));

import { wordTemplateCapability } from "./plugin";
import { keepImageRefs } from "./WordTemplateRichText";
import { clearImagePreviewCache, isPlaceableImage, resolveImagePreview } from "./sessionImages";

const dispatch = vi.fn();
const context = { capabilityId: "word_template", baseUrl: "/cap", teamId: "t", sessionId: "s 1", dispatch };
const DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

describe("word_template chat attachments: images vs Word files", () => {
  const fetchMock = vi.fn();
  const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);

  beforeEach(() => {
    fetchMock.mockReset();
    warn.mockClear();
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockImplementation(async () => new Response(JSON.stringify({ image_id: "img1" }), { status: 201 }));
  });
  afterEach(() => vi.unstubAllGlobals());

  it("sends an attached image to /images", async () => {
    await wordTemplateCapability.onChatAttachment?.(new File(["x"], "schema.png", { type: "image/png" }), context);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/cap/sessions/s%201/images");
    expect(init.method).toBe("POST");
    expect(init.headers.Authorization).toBe("Bearer tok");
    expect(init.body).toBeInstanceOf(FormData);
  });

  it("keeps sending a .docx to /attachments", async () => {
    await wordTemplateCapability.onChatAttachment?.(new File(["x"], "Archi.docx", { type: DOCX }), context);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe("/cap/sessions/s%201/attachments");
  });

  it("recognises images by MIME type, or by extension when the type is missing", () => {
    expect(isPlaceableImage(new File(["x"], "a", { type: "image/jpeg" }))).toBe(true);
    expect(isPlaceableImage(new File(["x"], "photo.JPG", { type: "" }))).toBe(true);
    expect(isPlaceableImage(new File(["x"], "vector.svg", { type: "image/svg+xml" }))).toBe(false);
    expect(isPlaceableImage(new File(["x"], "notes.pdf", { type: "application/pdf" }))).toBe(false);
  });

  it("ignores other files and never rejects on a failed upload", async () => {
    await wordTemplateCapability.onChatAttachment?.(new File(["x"], "notes.pdf", { type: "application/pdf" }), context);
    expect(fetchMock).not.toHaveBeenCalled();

    fetchMock.mockResolvedValueOnce(new Response("{}", { status: 415 }));
    await expect(
      wordTemplateCapability.onChatAttachment?.(new File(["x"], "x.png", { type: "image/png" }), context),
    ).resolves.toBeUndefined();
    expect(warn).toHaveBeenCalledTimes(1);
  });
});

describe("word_template img: references", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    clearImagePreviewCache();
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:img") }));
  });
  afterEach(() => vi.unstubAllGlobals());

  it("resolves img:<id> through the image route once, with the bearer", async () => {
    fetchMock.mockResolvedValue(new Response(new Blob(["png"]), { status: 200 }));
    const resolve = resolveImagePreview("/cap", "s 1");

    expect(await resolve("img:img1")).toBe("blob:img");
    expect(await resolve("img:img1")).toBe("blob:img");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/cap/sessions/s%201/images/img1");
    expect(init.headers.Authorization).toBe("Bearer tok");
  });

  it("leaves any other src alone", async () => {
    const resolve = resolveImagePreview("/cap", "s");
    expect(await resolve("https://example.org/a.png")).toBe("https://example.org/a.png");
    expect(await resolveImagePreview(undefined, "s")("img:img1")).toBe("img:img1");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("keeps img: sources in the reading view and neutralises unsafe ones", () => {
    expect(keepImageRefs("img:img2")).toBe("img:img2");
    expect(keepImageRefs("javascript:alert(1)")).toBe("");
  });
});

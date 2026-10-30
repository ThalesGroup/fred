// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { expect, it, vi } from "vitest";
import { previewQuery } from "./fixtures";

it("rejects unmodelled reads and destructive actions without an HTTP fallback", () => {
  const fetch = vi.spyOn(globalThis, "fetch");
  try {
    for (const request of ["/unknown", { url: "/control-plane/v1/import-export/reset", method: "POST" }]) {
      expect(previewQuery(request).error).toMatchObject({ status: 501 });
    }
    expect(fetch).not.toHaveBeenCalled();
  } finally {
    fetch.mockRestore();
  }
});

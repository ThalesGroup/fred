// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { previewFetch } from "./fixtures";

if (!import.meta.env.DEV || import.meta.env.MODE !== "swift-preview") {
  document.getElementById("root")!.textContent = "Cet aperçu nécessite make swift-preview.";
} else {
  window.fetch = previewFetch;
  // Network access outside fetch (XHR, EventSource, WebSocket) is denied by the HTML CSP.
  void import("../../common/config")
    .then(async ({ loadConfig }) => {
      await loadConfig();
      await import("./PreviewApp");
    })
    .catch((error: unknown) => {
      document.getElementById("root")!.textContent = String(error);
    });
}

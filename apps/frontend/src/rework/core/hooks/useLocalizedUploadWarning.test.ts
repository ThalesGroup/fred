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

// Pins the locale-fallback contract of the upload warning banner
// (MIGR-01.01): active language first, then "en", then hidden — so a
// deployment configuring only "en" still shows its notice to "fr" users, and
// a deployment configuring nothing renders nothing anywhere.

import { describe, expect, it } from "vitest";
import type { UploadWarning } from "../../../slices/controlPlane/controlPlaneOpenApi";
import { resolveUploadWarningMessage } from "./useLocalizedUploadWarning";

const warning: UploadWarning = {
  severity: "warning",
  messages: { en: "Do not upload classified documents.", fr: "Ne téléversez pas de documents classifiés." },
};

describe("resolveUploadWarningMessage", () => {
  it("picks the message matching the active language", () => {
    expect(resolveUploadWarningMessage(warning, "fr")).toBe("Ne téléversez pas de documents classifiés.");
  });

  it("strips the region subtag from i18next language tags", () => {
    expect(resolveUploadWarningMessage(warning, "fr-FR")).toBe("Ne téléversez pas de documents classifiés.");
  });

  it("falls back to en when the active language has no entry", () => {
    expect(resolveUploadWarningMessage(warning, "de")).toBe("Do not upload classified documents.");
  });

  it("returns null when neither the language nor en is configured", () => {
    expect(resolveUploadWarningMessage({ severity: "info", messages: { fr: "..." } }, "de")).toBeNull();
  });

  it("returns null when no warning is configured", () => {
    expect(resolveUploadWarningMessage(null, "fr")).toBeNull();
    expect(resolveUploadWarningMessage({ severity: "info" }, "fr")).toBeNull();
  });
});

// @vitest-environment happy-dom
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

import { act } from "react";
import { createRoot } from "react-dom/client";
import { expect, it, vi } from "vitest";

vi.mock("../../../../../hooks/useFrontendProperties", () => ({
  useFrontendProperties: () => ({
    agentsNicknameSingular: "Assistant",
    agentsNicknamePlural: "Assistants",
    siteDisplayName: "Acme",
  }),
}));

import i18n from "../../../../../i18n";
import { useAnalyticsTranslation } from "./useAnalyticsTranslation";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function Labels() {
  const { t } = useAnalyticsTranslation();
  return (
    <div>
      <span>{t("rework.analytics.tiles.agentsUsed.label")}</span>
      <span>{t("rework.analytics.tiles.conversations.def")}</span>
      <span>{t("rework.analytics.tiles.agentsUsed.caption", { count: 2 })}</span>
    </div>
  );
}

it("uses configured agent names in analytics labels and explanations", async () => {
  await i18n.changeLanguage("en");
  const container = document.createElement("div");
  const root = createRoot(container);
  act(() => root.render(<Labels />));
  expect(container.textContent).toContain("Assistants used");
  expect(container.textContent).toContain("across all assistants and spaces");
  expect(container.textContent).toContain("out of 2 existing assistants");
  act(() => root.unmount());
});

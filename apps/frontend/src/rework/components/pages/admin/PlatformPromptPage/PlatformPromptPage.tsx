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

import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup.tsx";
import PageHeader from "@shared/molecules/PageHeader/PageHeader.tsx";
import PlatformSystemPromptPane from "./PlatformSystemPromptPane";
import CreationAssistantPane from "./CreationAssistantPane";
import styles from "./PlatformPromptPage.module.css";

const TABS = ["system", "creation-assistant"] as const;
type Tab = (typeof TABS)[number];

/** Platform-wide prompts an admin owns, one tab each; `?tab=` keeps the choice on reload. */
export default function PlatformPromptPage() {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const tab: Tab = searchParams.get("tab") === "creation-assistant" ? "creation-assistant" : "system";

  const selectTab = (next: Tab) =>
    setSearchParams(
      (params) => {
        if (next === "system") params.delete("tab");
        else params.set("tab", next);
        return params;
      },
      { replace: true },
    );

  return (
    <div className={styles.page}>
      <PageHeader
        title={t("rework.platformPrompt.title")}
        tabs={
          <ButtonGroup
            size="small"
            color="secondary"
            variant="tabs"
            aria-label={t("rework.platformPrompt.tabs.aria")}
            selectedIndex={TABS.indexOf(tab)}
            onSelectedIndexChange={(index) => selectTab(TABS[index])}
            items={[
              { label: t("rework.platformPrompt.tabs.system") },
              { label: t("rework.platformPrompt.tabs.creationAssistant") },
            ]}
          />
        }
      />
      {tab === "system" ? <PlatformSystemPromptPane /> : <CreationAssistantPane />}
    </div>
  );
}

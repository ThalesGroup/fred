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

import Icon from "@shared/atoms/Icon/Icon.tsx";
import { type PropsWithChildren, useState } from "react";
import { useTranslation } from "react-i18next";
import styles from "./AdvancedSettingsSection.module.css";

/**
 * Collapsed-by-default "Advanced settings" of a capability's config form, drawn
 * as a plain text toggle with a chevron so it reads as part of the form rather
 * than a nested boxed accordion. Shared by the generic form and custom widgets.
 */
export function AdvancedSettingsSection({ children }: PropsWithChildren) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" className={styles.toggle} aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <span className={styles.toggleLabel}>{t("rework.teams.formAgent.advancedSettings")}</span>
        <Icon category="outlined" type={open ? "expand_less" : "expand_more"} />
      </button>
      {open && <div className={styles.fields}>{children}</div>}
    </>
  );
}

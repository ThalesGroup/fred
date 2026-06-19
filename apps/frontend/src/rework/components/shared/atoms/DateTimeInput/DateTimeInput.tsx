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

import { ComponentPropsWithRef, useId } from "react";
import { useTranslation } from "react-i18next";
import styles from "./DateTimeInput.module.scss";

export interface DateTimeInputProps extends Omit<ComponentPropsWithRef<"input">, "type"> {
  label?: string;
}

// Map app language codes to locales that render 24h time in datetime-local pickers.
// Browsers use the element's resolved `lang` to format the native picker UI.
const LANG_TO_24H_LOCALE: Record<string, string> = {
  fr: "fr-FR",
  en: "en-GB",
};

export default function DateTimeInput({ label, ...props }: DateTimeInputProps) {
  const id = useId();
  const { i18n } = useTranslation();
  const lang = i18n.language?.split("-")[0] ?? "en";
  const pickerLang = LANG_TO_24H_LOCALE[lang] ?? "fr-FR";

  return (
    <div className={`${styles.wrapper} ${props.disabled ? styles.disabled : ""}`}>
      {label && (
        <label className={styles.label} htmlFor={id}>
          {label}
        </label>
      )}
      <input id={id} type="datetime-local" lang={pickerLang} className={styles.input} {...props} />
    </div>
  );
}

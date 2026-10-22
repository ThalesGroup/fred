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
import Switch from "@shared/atoms/Switch/Switch.tsx";
import { Spinner } from "@shared/atoms/Spinner/Spinner.tsx";
import { useConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider";
import PageHeader from "@shared/molecules/PageHeader/PageHeader.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { normalizeApiError } from "@core/errors/normalizeApiError.ts";
import {
  useNotificationTypesQuery,
  useSetNotificationTypeMutation,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { NotificationType } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./NotificationsPage.module.css";

/**
 * Platform-wide switch per notification type. The list comes from the backend
 * registry; each type is named from its value, so a type this frontend does not
 * know yet still shows, under its raw value.
 */
export default function NotificationsPage() {
  const { t } = useTranslation();
  const { showError } = useToast();
  const { showConfirmationDialog } = useConfirmationDialog();
  const { data, isLoading, isFetching, isError } = useNotificationTypesQuery();
  const [setType, { isLoading: isSaving }] = useSetNotificationTypeMutation();
  const locked = isFetching || isSaving;

  const save = async (type: NotificationType, enabled: boolean) => {
    try {
      await setType({ notificationType: type, setNotificationTypeRequest: { enabled } }).unwrap();
    } catch (error: unknown) {
      showError({ summary: t("rework.notificationSettings.saveFailed"), detail: normalizeApiError(error).detail });
    }
  };

  // Off deletes the notifications already sent, for everyone: confirm it first.
  const toggle = (type: NotificationType, name: string, enabled: boolean) => {
    if (enabled) {
      void save(type, true);
      return;
    }
    showConfirmationDialog({
      title: t("rework.notificationSettings.turnOff.title", { name }),
      message: t("rework.notificationSettings.turnOff.message"),
      confirmButtonLabel: t("rework.notificationSettings.turnOff.confirm"),
      criticalAction: true,
      onConfirm: () => void save(type, false),
    });
  };

  return (
    <div className={styles.page}>
      <PageHeader title={t("rework.notificationSettings.title")} subtitle={t("rework.notificationSettings.subtitle")} />

      <p className={styles.hint}>{t("rework.notificationSettings.hint")}</p>

      {isError && (
        <p className={styles.error} role="alert">
          {t("rework.notificationSettings.loadFailed")}
        </p>
      )}
      {isLoading && <Spinner />}

      <ul className={styles.types}>
        {data?.items.map(({ type, enabled }) => {
          const name = t(`rework.notificationSettings.types.${type}.name`, { defaultValue: type });
          return (
            <li key={type} className={styles.tile}>
              <span className={styles.text}>
                <span className={styles.name}>{name}</span>
                <span className={styles.description}>
                  {t(`rework.notificationSettings.types.${type}.description`, { defaultValue: "" })}
                </span>
              </span>
              <Switch
                size="small"
                checked={enabled}
                disabled={locked}
                onChange={(event) => toggle(type, name, event.target.checked)}
                aria-label={t("rework.notificationSettings.toggleLabel", { name })}
              />
            </li>
          );
        })}
      </ul>
    </div>
  );
}

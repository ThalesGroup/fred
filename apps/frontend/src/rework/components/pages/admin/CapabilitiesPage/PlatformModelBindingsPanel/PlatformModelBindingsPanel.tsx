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

// Platform-wide chat model binding admin panel — chat-only, since V1's only
// real consumer is chat, so this panel edits exactly one binding, not a
// fixed 4-row list. Lets a platform operator assert one
// authoritative (provider, name, settings) binding that every runtime pod's
// own `models_catalog.yaml` resolution is bypassed for — the concrete lever
// for a deployment where the operator knows what's actually
// reachable/licensed and no pod's shipped catalog does. Opened as a drawer
// (not a page) from CapabilitiesPage's Models tab, sibling to
// CapabilityTeamMatrixDrawer.tsx — a single binding, so a full page is
// disproportionate.
//
// Settings are edited as raw JSON text (TextArea atom), not a key/value rows
// editor: `ModelBindingSettings` is a strict, typed, generated shape
// (bool/int/float/string fields), and a rows editor that always stores
// `string` per row cannot represent that without lossy coercion. The
// JSON editor parses explicitly, reports invalid JSON inline, and only
// submits when the parsed value is a JSON object — the server's strict
// `ModelBindingSettings` contract (extra="forbid", no credential/auth/
// header/cookie/client-object field) remains the actual security boundary;
// this editor does not re-implement any client-side credential-key check.

import Button from "@shared/atoms/Button/Button.tsx";
import { DeleteIconButton } from "@shared/atoms/DeleteIconButton/DeleteIconButton";
import TextArea from "@shared/atoms/TextArea/TextArea.tsx";
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import { InlineDrawer } from "@shared/molecules/InlineDrawer/InlineDrawer.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  useDeletePlatformModelBindingMutation,
  usePlatformModelBindingQuery,
  useSetPlatformModelBindingMutation,
} from "../../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { ModelBinding, ModelBindingSettings } from "../../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./PlatformModelBindingsPanel.module.css";

interface PlatformModelBindingsPanelProps {
  open: boolean;
  onClose: () => void;
}

/** Parses the settings textarea. `null` means "not a JSON object" (including
 * valid-but-wrong-shaped JSON like an array, a string, or `null` itself) —
 * treated the same as a syntax error, since the request body requires an
 * object. Distinguishing "no error" from "parses but isn't an object" lets
 * the caller show one consistent inline message either way. */
function parseSettingsObject(text: string): { value: Record<string, unknown> } | { error: true } {
  let parsed: unknown;
  try {
    parsed = text.trim() === "" ? {} : JSON.parse(text);
  } catch {
    return { error: true };
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    return { error: true };
  }
  return { value: parsed as Record<string, unknown> };
}

export function PlatformModelBindingsPanel({ open, onClose }: PlatformModelBindingsPanelProps) {
  const { t } = useTranslation();
  const { showSuccess, showError } = useToast();
  const { data, isLoading, isError } = usePlatformModelBindingQuery();
  const [setBinding, { isLoading: isSaving }] = useSetPlatformModelBindingMutation();
  const [deleteBinding, { isLoading: isDeleting }] = useDeletePlatformModelBindingMutation();
  const busy = isSaving || isDeleting;

  const binding = data?.binding ?? null;

  const [isEditing, setIsEditing] = useState(false);
  const [provider, setProvider] = useState("");
  const [name, setName] = useState("");
  const [settingsText, setSettingsText] = useState("{}");

  // Editing state does not survive the drawer closing — reopening always
  // starts from the current server state, never a stale in-progress edit.
  useEffect(() => {
    if (!open) setIsEditing(false);
  }, [open]);

  const startEdit = () => {
    setIsEditing(true);
    setProvider(binding?.provider ?? "");
    setName(binding?.name ?? "");
    setSettingsText(JSON.stringify(binding?.settings ?? {}, null, 2));
  };

  const cancelEdit = () => setIsEditing(false);

  const parsedSettings = parseSettingsObject(settingsText);
  const settingsInvalid = "error" in parsedSettings;
  const canSave = provider.trim() !== "" && name.trim() !== "" && !settingsInvalid;

  const handleSave = async () => {
    if (!canSave || "error" in parsedSettings) return;
    try {
      await setBinding({
        setPlatformModelBindingRequest: {
          binding: {
            // `provider` stays a free-text TextInput (not a generated-enum
            // picker) — this cast only satisfies the now-closed generated
            // union type; the server's `ModelBinding` validator is the
            // actual authority and rejects anything outside it with 422.
            provider: provider.trim() as ModelBinding["provider"],
            name: name.trim(),
            settings: parsedSettings.value as ModelBindingSettings,
          },
        },
      }).unwrap();
      showSuccess({ summary: t("rework.admin.platformModelBindings.saveToast") });
      setIsEditing(false);
    } catch {
      showError({ summary: t("rework.admin.platformModelBindings.saveError") });
    }
  };

  const handleDelete = async () => {
    try {
      await deleteBinding().unwrap();
      showSuccess({ summary: t("rework.admin.platformModelBindings.deleteToast") });
      setIsEditing(false);
    } catch {
      showError({ summary: t("rework.admin.platformModelBindings.deleteError") });
    }
  };

  return (
    <InlineDrawer open={open} onClose={onClose} title={t("rework.admin.platformModelBindings.title")} width="480px">
      <div className={styles.body}>
        <p className={styles.hint}>{t("rework.admin.platformModelBindings.subtitle")}</p>

        {isLoading && <p className={styles.hint}>{t("rework.admin.platformModelBindings.loading")}</p>}
        {isError && <p className={styles.statusError}>{t("rework.admin.platformModelBindings.loadError")}</p>}

        {!isLoading && !isError && (
          <div className={styles.row}>
            <div className={styles.rowHeader}>
              <div className={styles.rowMain}>
                <span className={styles.capabilityLabel}>
                  {t("rework.admin.platformModelBindings.capability.chat")}
                </span>
                <span className={styles.stateText}>
                  {binding
                    ? t("rework.admin.platformModelBindings.boundState", {
                        provider: binding.provider,
                        name: binding.name,
                      })
                    : t("rework.admin.platformModelBindings.podDefault")}
                </span>
              </div>
              <div className={styles.rowActions}>
                {binding && !isEditing && (
                  <DeleteIconButton
                    size="small"
                    aria-label={t("rework.admin.platformModelBindings.deleteAction")}
                    onClick={() => void handleDelete()}
                    disabled={busy}
                  />
                )}
                {!isEditing && (
                  <Button color="on-surface" variant="outlined" size="small" onClick={startEdit} disabled={busy}>
                    {t("rework.admin.platformModelBindings.editAction")}
                  </Button>
                )}
              </div>
            </div>

            {isEditing && (
              <form
                className={styles.editForm}
                onSubmit={(e) => {
                  e.preventDefault();
                  void handleSave();
                }}
              >
                <TextInput
                  label={t("rework.admin.platformModelBindings.form.provider")}
                  value={provider}
                  onChange={(e) => setProvider(e.target.value)}
                  disabled={busy}
                  required
                />
                <TextInput
                  label={t("rework.admin.platformModelBindings.form.name")}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  disabled={busy}
                  required
                />
                <TextArea
                  label={t("rework.admin.platformModelBindings.form.settingsTitle")}
                  value={settingsText}
                  onChange={(e) => setSettingsText(e.target.value)}
                  error={settingsInvalid ? t("rework.admin.platformModelBindings.form.settingsInvalidJson") : undefined}
                  explanation={settingsInvalid ? undefined : t("rework.admin.platformModelBindings.form.settingsHint")}
                  rows={8}
                  disabled={busy}
                />

                <div className={styles.formActions}>
                  <Button color="on-surface" variant="text" size="small" onClick={cancelEdit} disabled={busy}>
                    {t("rework.admin.platformModelBindings.form.cancel")}
                  </Button>
                  <Button color="primary" variant="filled" size="small" type="submit" disabled={busy || !canSave}>
                    {t("rework.admin.platformModelBindings.form.save")}
                  </Button>
                </div>
              </form>
            )}
          </div>
        )}
      </div>
    </InlineDrawer>
  );
}

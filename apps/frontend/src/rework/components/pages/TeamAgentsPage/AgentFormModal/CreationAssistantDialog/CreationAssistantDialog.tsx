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

import Icon from "@shared/atoms/Icon/Icon";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { Spinner } from "@shared/atoms/Spinner/Spinner";
import TextArea from "@shared/atoms/TextArea/TextArea";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import { ConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialog";
import { Dialog } from "@shared/molecules/Dialog/Dialog";
import { PromptEditor } from "@shared/molecules/PromptEditor/PromptEditor";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useDraftAgentMutation } from "../../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type {
  AgentDraftResult,
  CapabilityCatalogEntry,
} from "../../../../../../slices/controlPlane/controlPlaneOpenApi";
import {
  type AppliedDraft,
  availableRecommendedIds,
  buildAgentDraftRequest,
  type DraftItem,
  type DraftTargets,
  DRAFT_DESCRIPTION_MAX_LENGTH,
  agentDraftErrorKey,
  offeredDraftItems,
  type OverwrittenItem,
  overwrittenItems,
  REASONING_LABEL_KEY,
  selectedDraft,
} from "./creationAssistant";
import styles from "./CreationAssistantDialog.module.css";

const KEY = "rework.teams.formAgent.creationAssistant";

type CreationAssistantDialogProps = {
  open: boolean;
  teamId: string;
  templateId: string;
  /** The template's capabilities this team may enable; offered to the assistant. */
  capabilities: CapabilityCatalogEntry[];
  /** False when the template has no prompt field: the drafted prompt cannot be applied. */
  hasPromptField: boolean;
  /** True when the form offers reasoning: the review then always proposes it, ticked. */
  offersReasoning: boolean;
  /** What the user already wrote ("" when untouched); replacing it needs a confirmation. */
  current: DraftTargets;
  onApply: (draft: AppliedDraft) => void;
  onClose: () => void;
};

/** Two steps: describe the agent in plain words, then pick which drafted values to apply. */
export function CreationAssistantDialog({
  open,
  teamId,
  templateId,
  capabilities,
  hasPromptField,
  offersReasoning,
  current,
  onApply,
  onClose,
}: CreationAssistantDialogProps) {
  const { t, i18n } = useTranslation();
  const [draftAgent] = useDraftAgentMutation();
  const [description, setDescription] = useState("");
  const [result, setResult] = useState<AgentDraftResult | null>(null);
  // Everything is ticked by default; the user unticks what they do not want.
  const [ticked, setTicked] = useState<ReadonlySet<DraftItem>>(new Set());
  const [selectedIds, setSelectedIds] = useState<ReadonlySet<string>>(new Set());
  const [reasoningTicked, setReasoningTicked] = useState(true);
  const [toConfirm, setToConfirm] = useState<OverwrittenItem[] | null>(null);
  const [errorKey, setErrorKey] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  // The in-flight request, aborted on close so a late answer never lands.
  const pending = useRef<{ abort: () => void } | null>(null);

  // The description survives a close, so a user can reopen and retry.
  useEffect(() => {
    if (!open) return;
    setResult(null);
    setErrorKey(null);
    setToConfirm(null);
    return () => {
      pending.current?.abort();
      pending.current = null;
      setLoading(false);
    };
  }, [open]);

  const capabilityById = new Map(capabilities.map((capability) => [capability.id, capability]));
  const recommendedIds = result
    ? availableRecommendedIds(result.capability_ids ?? [], new Set(capabilityById.keys()))
    : [];
  const items = result ? offeredDraftItems(result, hasPromptField) : [];
  const fieldItems = (["name", "role", "description"] as const).filter((item) => items.includes(item));
  const tickedIds = recommendedIds.filter((id) => selectedIds.has(id));
  const reasoningOn = offersReasoning && reasoningTicked;
  const draft = result ? selectedDraft(result, ticked, tickedIds, reasoningOn) : {};
  // The capabilities column: the reasoning tile (when offered) then the recommendations.
  const columnTotal = recommendedIds.length + (offersReasoning ? 1 : 0);
  const columnTicked = tickedIds.length + (reasoningOn ? 1 : 0);
  const nothingTicked = Object.keys(draft).length === 0;

  const runDraft = async () => {
    if (!description.trim() || loading) return;
    setLoading(true);
    setErrorKey(null);
    const request = draftAgent({
      teamId,
      templateId: encodeURIComponent(templateId),
      agentDraftRequest: buildAgentDraftRequest({
        description,
        language: i18n.language,
        agentName: current.name,
        agentRole: current.role,
        capabilities,
        translate: (key) => t(key, { defaultValue: key }),
      }),
    });
    pending.current = request;
    try {
      const drafted = await request.unwrap();
      if (pending.current !== request) return;
      setResult(drafted);
      setTicked(new Set(offeredDraftItems(drafted, hasPromptField)));
      setSelectedIds(new Set(availableRecommendedIds(drafted.capability_ids ?? [], new Set(capabilityById.keys()))));
      setReasoningTicked(true);
    } catch (error) {
      if (pending.current !== request) return;
      setErrorKey(agentDraftErrorKey(error));
    } finally {
      if (pending.current === request) {
        pending.current = null;
        setLoading(false);
      }
    }
  };

  const apply = () => {
    const replaced = overwrittenItems(draft, current, new Set(capabilityById.keys()));
    if (replaced.length > 0) setToConfirm(replaced);
    else onApply(draft);
  };

  const toggleItem = (item: DraftItem) =>
    setTicked((previous) => {
      const next = new Set(previous);
      if (next.has(item)) next.delete(item);
      else next.add(item);
      return next;
    });

  const toggleCapability = (id: string) =>
    setSelectedIds((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const toggleCapabilityColumn = () => {
    const allTicked = columnTicked === columnTotal;
    setSelectedIds(new Set(allTicked ? [] : recommendedIds));
    setReasoningTicked(!allTicked);
  };

  const tickedFields = fieldItems.filter((item) => ticked.has(item));
  const toggleFields = () =>
    setTicked((previous) => {
      const next = new Set(previous);
      for (const item of fieldItems) {
        if (tickedFields.length === fieldItems.length) next.delete(item);
        else next.add(item);
      }
      return next;
    });

  const reviewing = result !== null;

  return (
    <>
      <Dialog
        open={open}
        title={t(`${KEY}.title`)}
        confirmLabel={reviewing ? t(`${KEY}.apply`) : t(`${KEY}.generate`)}
        confirmDisabled={loading || (reviewing ? nothingTicked : !description.trim())}
        onConfirm={() => {
          if (reviewing) apply();
          else void runDraft();
        }}
        onCancel={onClose}
        cancelLabel={t("rework.cancel")}
        maxWidth={900}
        titlePrefix={
          reviewing ? (
            <Tooltip text={t(`${KEY}.editDescription`)}>
              <IconButton
                variant="icon"
                size="medium"
                icon={{ category: "outlined", type: "arrow_back" }}
                aria-label={t(`${KEY}.editDescription`)}
                onClick={() => setResult(null)}
              />
            </Tooltip>
          ) : undefined
        }
        titleAddon={reviewing ? <p className={styles.titleHint}>{t(`${KEY}.selectHint`)}</p> : undefined}
        footerStart={
          reviewing ? (
            <p className={styles.hint}>{t(`${KEY}.applyHint`)}</p>
          ) : loading ? (
            <LoadingRow label={t(`${KEY}.loading`)} />
          ) : undefined
        }
        compactTitle
        className={reviewing ? styles.reviewDialog : undefined}
      >
        {reviewing ? (
          <div className={`${styles.content} ${styles.reviewContent}`}>
            <div className={styles.reviewBody}>
              {fieldItems.length > 0 && (
                <SectionPanel
                  title={t(`${KEY}.identityHeading`)}
                  state={groupState(tickedFields.length, fieldItems.length)}
                  onToggle={toggleFields}
                  className={styles.sideColumn}
                >
                  {fieldItems.map((item) => (
                    <SelectableTile key={item} checked={ticked.has(item)} onToggle={() => toggleItem(item)}>
                      <span className={styles.fieldLabel}>{t(`${KEY}.fields.${item}`)}</span>
                      <span className={styles.fieldValue}>{result[item]}</span>
                    </SelectableTile>
                  ))}
                </SectionPanel>
              )}
              {items.includes("systemPrompt") && (
                // Only the header toggles: the prompt itself stays free for text selection.
                <SectionPanel
                  title={t(`${KEY}.promptHeading`)}
                  state={ticked.has("systemPrompt") ? "true" : "false"}
                  onToggle={() => toggleItem("systemPrompt")}
                  className={styles.promptColumn}
                >
                  <PromptEditor
                    label={t(`${KEY}.promptHeading`)}
                    hideLabel
                    value={result.system_prompt}
                    onChange={() => {}}
                    readOnly
                    fillHeight
                    highlighted={ticked.has("systemPrompt")}
                  />
                </SectionPanel>
              )}
              {(capabilities.length > 0 || offersReasoning) && (
                <SectionPanel
                  title={t(`${KEY}.capabilitiesHeading`)}
                  state={columnTotal > 0 ? groupState(columnTicked, columnTotal) : null}
                  onToggle={toggleCapabilityColumn}
                  className={styles.sideColumn}
                >
                  {columnTotal > 0 && (
                    <ul className={styles.capabilityList}>
                      {offersReasoning && (
                        <li>
                          <SelectableTile checked={reasoningTicked} onToggle={() => setReasoningTicked((on) => !on)}>
                            {t(REASONING_LABEL_KEY)}
                          </SelectableTile>
                        </li>
                      )}
                      {recommendedIds.map((id) => {
                        const capability = capabilityById.get(id);
                        return (
                          <li key={id}>
                            <SelectableTile checked={selectedIds.has(id)} onToggle={() => toggleCapability(id)}>
                              {capability ? t(capability.name, { defaultValue: capability.name }) : id}
                            </SelectableTile>
                          </li>
                        );
                      })}
                    </ul>
                  )}
                  {recommendedIds.length === 0 && capabilities.length > 0 && !offersReasoning && (
                    <p className={styles.hint}>{t(`${KEY}.noCapabilities`)}</p>
                  )}
                </SectionPanel>
              )}
            </div>
          </div>
        ) : (
          <div className={styles.content}>
            <p className={styles.intro}>{t(`${KEY}.intro`)}</p>
            <TextArea
              label={t(`${KEY}.descriptionLabel`)}
              placeholder={t(`${KEY}.descriptionPlaceholder`)}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              maxLength={DRAFT_DESCRIPTION_MAX_LENGTH}
              rows={8}
              disabled={loading}
            />
            {errorKey && !loading && (
              <p className={styles.error} role="alert">
                {t(errorKey)}
              </p>
            )}
          </div>
        )}
      </Dialog>
      <ConfirmationDialog
        open={toConfirm !== null}
        criticalAction
        title={t(`${KEY}.overwrite.title`)}
        message={t(`${KEY}.overwrite.message`)}
        details={
          <ul className={styles.overwriteList}>
            {(toConfirm ?? []).map((item) => (
              <li key={item}>{t(`${KEY}.overwrite.items.${item}`)}</li>
            ))}
          </ul>
        }
        confirmLabel={t(`${KEY}.overwrite.confirm`)}
        cancelLabel={t("rework.cancel")}
        onConfirm={() => {
          setToConfirm(null);
          onApply(draft);
        }}
        onCancel={() => setToConfirm(null)}
      />
    </>
  );
}

type CheckState = "true" | "mixed" | "false";

const groupState = (tickedCount: number, total: number): CheckState =>
  tickedCount === 0 ? "false" : tickedCount === total ? "true" : "mixed";

function StatusIcon({ state, className }: { state: CheckState; className: string }) {
  const icon = state === "true" ? "check_circle" : state === "mixed" ? "remove_circle" : "radio_button_unchecked";
  return (
    <span className={className}>
      <Icon category="outlined" type={icon} filled={state !== "false"} />
    </span>
  );
}

/** A review column: a header that (de)selects the whole section, over a scrolling body. */
function SectionPanel({
  title,
  state,
  onToggle,
  className,
  children,
}: {
  title: string;
  /** Null when the section has nothing to select: the header is a plain title. */
  state: CheckState | null;
  onToggle: () => void;
  className: string;
  children: ReactNode;
}) {
  return (
    <section className={`${styles.panel} ${className}`}>
      {state === null ? (
        <h3 className={styles.sectionHeader}>
          <span className={styles.sectionTitle}>{title}</span>
        </h3>
      ) : (
        <button type="button" role="checkbox" aria-checked={state} className={styles.sectionHeader} onClick={onToggle}>
          <span className={styles.sectionTitle}>{title}</span>
          <StatusIcon state={state} className={styles.statusIcon} />
        </button>
      )}
      <div className={styles.panelBody}>{children}</div>
    </section>
  );
}

/** A whole-tile toggle; the status icon sits top-right so the values start at the left edge. */
function SelectableTile({
  checked,
  onToggle,
  children,
}: {
  checked: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  const state = checked ? "true" : "false";
  return (
    <button type="button" role="checkbox" aria-checked={state} className={styles.tile} onClick={onToggle}>
      <span className={styles.tileContent}>{children}</span>
      <StatusIcon state={state} className={styles.statusIcon} />
    </button>
  );
}

function LoadingRow({ label }: { label: string }) {
  return (
    <p className={styles.loading} role="status">
      <Spinner size={18} decorative />
      {label}
    </p>
  );
}

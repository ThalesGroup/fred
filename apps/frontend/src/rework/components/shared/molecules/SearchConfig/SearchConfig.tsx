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

import { type CSSProperties, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type {
  ContextPromptSummary,
  EffectiveChatOptions,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { type SearchPolicyName } from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { DocumentLibraryScopePicker } from "@shared/molecules/DocumentLibraryScopePicker/DocumentLibraryScopePicker";
import { ContextPromptPicker } from "@shared/molecules/ContextPromptPicker/ContextPromptPicker";
import type { IconProps } from "@shared/atoms/Icon/Icon.tsx";
import MenuPopover from "@shared/molecules/MenuPopover/MenuPopover.tsx";
import MenuPopoverItem from "@shared/molecules/MenuPopover/MenuPopoverItem.tsx";
import styles from "./SearchConfig.module.css";

type RagScope = "corpus_only" | "hybrid" | "general_only";
type OpenMenu = "picker" | "policy" | "scope" | "prompts" | null;

const PROMPTS_MENU_MAX_HEIGHT_PX = 480;

const PICKER_VIEWPORT_MARGIN_PX = 16;
const PICKER_DESKTOP_MAX_HEIGHT_PX = 640;
const PICKER_MOBILE_MAX_HEIGHT_PX = 480;
const PICKER_MIN_HEIGHT_PX = 160;

interface SearchConfigProps {
  teamId: string;
  onAttach: () => void;
  onRequestClose?: () => void;
  selectedLibraryIds: string[];
  onSelectedLibraryIdsChange: (ids: string[]) => void;
  selectedDocumentUids: string[];
  onSelectedDocumentUidsChange: (uids: string[]) => void;
  searchPolicy: SearchPolicyName;
  onSearchPolicyChange: (value: SearchPolicyName) => void;
  ragScope: RagScope;
  onRagScopeChange: (value: RagScope) => void;
  contextPrompts: ContextPromptSummary[];
  contextPromptIds: string[];
  onContextPromptIdsChange: (ids: string[]) => void;
  options?: EffectiveChatOptions | null;
}

interface SelectOption<T extends string> {
  value: T;
  label: string;
}

function SearchConfigSelect<T extends string>({
  icon,
  label,
  title,
  value,
  options,
  open,
  onToggle,
  onChange,
}: {
  icon: IconProps;
  label: string;
  title: string;
  value: T;
  options: SelectOption<T>[];
  open: boolean;
  onToggle: () => void;
  onChange: (value: T) => void;
}) {
  const selected = options.find((option) => option.value === value) ?? options[0];

  return (
    <div className={styles.rowWrap}>
      <MenuPopoverItem
        icon={icon}
        label={label}
        value={selected.label}
        trailingIcon="chevron_right"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`${title}: ${selected.label}`}
        onClick={onToggle}
      />

      {open && (
        <ul className={styles.selectMenu} role="listbox" aria-label={title}>
          {options.map((option) => {
            const isActive = option.value === value;
            return (
              <li key={option.value} className={styles.menuItemWrap}>
                <button
                  type="button"
                  role="option"
                  aria-selected={isActive}
                  className={styles.menuItem}
                  data-active={isActive}
                  onClick={() => onChange(option.value)}
                >
                  <span className={styles.menuItemLabel}>{option.label}</span>
                  {isActive && (
                    <span className={`${styles.menuItemCheck} material-symbols-outlined`} aria-hidden>
                      check
                    </span>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function buildPickerLabel(params: {
  selectedDocumentUids: string[];
  effectiveLibraryIds: string[];
  t: ReturnType<typeof useTranslation>["t"];
}) {
  const { selectedDocumentUids, effectiveLibraryIds, t } = params;
  if (effectiveLibraryIds.length > 0 && selectedDocumentUids.length > 0) {
    return `${t("chatbot.composerSettings.librariesCount", { count: effectiveLibraryIds.length })}, ${t(
      "chatbot.composerSettings.documentsCount",
      { count: selectedDocumentUids.length },
    )}`;
  }
  if (selectedDocumentUids.length > 0) {
    return t("chatbot.composerSettings.documentsCount", { count: selectedDocumentUids.length });
  }
  if (effectiveLibraryIds.length > 0) {
    return t("chatbot.composerSettings.librariesCount", { count: effectiveLibraryIds.length });
  }
  return t("chatbot.composerSettings.noDocumentsSelected");
}

export function SearchConfig({
  teamId,
  onAttach,
  onRequestClose,
  selectedLibraryIds,
  onSelectedLibraryIdsChange,
  selectedDocumentUids,
  onSelectedDocumentUidsChange,
  searchPolicy,
  onSearchPolicyChange,
  ragScope,
  onRagScopeChange,
  contextPrompts,
  contextPromptIds,
  onContextPromptIdsChange,
  options = null,
}: SearchConfigProps) {
  const { t } = useTranslation();
  const [openMenu, setOpenMenu] = useState<OpenMenu>(null);
  const [pickerMenuMaxHeight, setPickerMenuMaxHeight] = useState(360);
  const rootRef = useRef<HTMLDivElement>(null);
  const pickerWrapRef = useRef<HTMLDivElement>(null);
  const promptsWrapRef = useRef<HTMLDivElement>(null);

  const showAttachFiles = options?.attach_files === true;
  const showLibraries = options?.libraries_selection === true;
  const showDocuments = options?.documents_selection === true;
  const showSearchPolicy = options?.search_policy_selection === true;
  const showRagScope = options?.rag_scope_selection === true;
  const boundLibraryIds = options?.bound_library_ids ?? [];
  const hasBoundLibraries = boundLibraryIds.length > 0;
  const effectiveLibraryIds = hasBoundLibraries ? boundLibraryIds : selectedLibraryIds;

  const searchPolicies = useMemo<SelectOption<SearchPolicyName>[]>(
    () => [
      { value: "strict", label: t("search.strict") },
      { value: "hybrid", label: t("search.hybrid") },
      { value: "semantic", label: t("search.semantic") },
    ],
    [t],
  );

  const ragScopes = useMemo<SelectOption<RagScope>[]>(
    () => [
      { value: "corpus_only", label: t("chatbot.composerSettings.scopeCorpus") },
      { value: "hybrid", label: t("chatbot.composerSettings.scopeCorpusAndWeb") },
      { value: "general_only", label: t("chatbot.composerSettings.scopeGeneral") },
    ],
    [t],
  );

  const pickerTitle = showDocuments
    ? t("chatbot.composerSettings.documentPickerTitle")
    : t("agentTuning.fields.chat_options_libraries_selection.title");
  const pickerLabel = buildPickerLabel({
    selectedDocumentUids,
    effectiveLibraryIds,
    t,
  });
  const promptsLabel =
    contextPromptIds.length > 0
      ? t("chatbot.contextPrompts.activeCount", { count: contextPromptIds.length })
      : t("chatbot.contextPrompts.none");

  useEffect(() => {
    if (!openMenu) return;

    const handleMouseDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpenMenu(null);
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpenMenu(null);
    };

    document.addEventListener("mousedown", handleMouseDown);
    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("mousedown", handleMouseDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [openMenu]);

  useEffect(() => {
    // Both the document picker and the prompts list use `.pickerMenu`, which
    // anchors `bottom: 0` and grows upward. Without clamping its height to the
    // space above the row, a tall list overflows past the top of the viewport.
    const wrapRef = openMenu === "prompts" ? promptsWrapRef : openMenu === "picker" ? pickerWrapRef : null;
    if (!wrapRef) return;

    const desktopCap = openMenu === "prompts" ? PROMPTS_MENU_MAX_HEIGHT_PX : PICKER_DESKTOP_MAX_HEIGHT_PX;

    const updatePickerMenuMaxHeight = () => {
      const rect = wrapRef.current?.getBoundingClientRect();
      if (!rect) return;

      const viewportHeight = window.visualViewport?.height ?? window.innerHeight;
      const viewportWidth = window.visualViewport?.width ?? window.innerWidth;
      const heightCap = viewportWidth <= 720 ? PICKER_MOBILE_MAX_HEIGHT_PX : desktopCap;
      const availableHeight = Math.floor(Math.min(rect.bottom, viewportHeight) - PICKER_VIEWPORT_MARGIN_PX);
      setPickerMenuMaxHeight(Math.min(heightCap, Math.max(PICKER_MIN_HEIGHT_PX, availableHeight)));
    };

    updatePickerMenuMaxHeight();

    window.addEventListener("resize", updatePickerMenuMaxHeight);
    window.addEventListener("scroll", updatePickerMenuMaxHeight, true);
    window.visualViewport?.addEventListener("resize", updatePickerMenuMaxHeight);
    window.visualViewport?.addEventListener("scroll", updatePickerMenuMaxHeight);

    return () => {
      window.removeEventListener("resize", updatePickerMenuMaxHeight);
      window.removeEventListener("scroll", updatePickerMenuMaxHeight, true);
      window.visualViewport?.removeEventListener("resize", updatePickerMenuMaxHeight);
      window.visualViewport?.removeEventListener("scroll", updatePickerMenuMaxHeight);
    };
  }, [openMenu]);

  const pickerMenuStyle: CSSProperties = {
    maxHeight: pickerMenuMaxHeight,
  };

  return (
    <MenuPopover
      ref={rootRef}
      className={styles.searchConfigBox}
      groups={[
        [
          showAttachFiles && (
            <MenuPopoverItem
              key="attach"
              icon={{ category: "outlined", type: "attach_file" }}
              label={t("chatbot.attachFiles")}
              trailingIcon="add"
              onClick={() => {
                onAttach();
                onRequestClose?.();
              }}
            />
          ),
        ],
        [
          <div key="prompts" ref={promptsWrapRef} className={styles.rowWrap}>
            <MenuPopoverItem
              icon={{ category: "outlined", type: "auto_awesome" }}
              label={t("chatbot.contextPrompts.rowLabel")}
              value={promptsLabel}
              trailingIcon="chevron_right"
              aria-haspopup="dialog"
              aria-expanded={openMenu === "prompts"}
              onClick={() => setOpenMenu((current) => (current === "prompts" ? null : "prompts"))}
            />

            {openMenu === "prompts" && (
              <div
                className={styles.pickerMenu}
                role="dialog"
                aria-label={t("chatbot.contextPrompts.title")}
                style={pickerMenuStyle}
              >
                <div className={styles.pickerMenuBody}>
                  <ContextPromptPicker
                    prompts={contextPrompts}
                    selectedIds={contextPromptIds}
                    onChange={onContextPromptIdsChange}
                  />
                </div>
              </div>
            )}
          </div>,
        ],
        [
          (showLibraries || showDocuments) && (
            <div key="picker" ref={pickerWrapRef} className={styles.rowWrap}>
              <MenuPopoverItem
                icon={{ category: "outlined", type: "description" }}
                label={pickerTitle}
                value={pickerLabel}
                trailingIcon="chevron_right"
                aria-haspopup="dialog"
                aria-expanded={openMenu === "picker"}
                onClick={() => setOpenMenu((current) => (current === "picker" ? null : "picker"))}
              />

              {openMenu === "picker" && (
                <div className={styles.pickerMenu} role="dialog" aria-label={pickerTitle} style={pickerMenuStyle}>
                  <div className={styles.pickerMenuBody}>
                    <DocumentLibraryScopePicker
                      teamId={teamId}
                      selectedTagIds={effectiveLibraryIds}
                      onChange={onSelectedLibraryIdsChange}
                      selectedDocumentUids={showDocuments ? selectedDocumentUids : undefined}
                      onDocumentsChange={showDocuments ? onSelectedDocumentUidsChange : undefined}
                      disableLibrarySelection={hasBoundLibraries}
                    />
                  </div>
                </div>
              )}
            </div>
          ),
          showSearchPolicy && (
            <SearchConfigSelect
              key="policy"
              icon={{ category: "outlined", type: "search" }}
              label={t("chatbot.composerSettings.searchPolicyRowLabel")}
              title={t("chatbot.composerSettings.searchPolicyTitle")}
              value={searchPolicy}
              options={searchPolicies}
              open={openMenu === "policy"}
              onToggle={() => setOpenMenu((current) => (current === "policy" ? null : "policy"))}
              onChange={(value) => {
                onSearchPolicyChange(value);
                setOpenMenu(null);
              }}
            />
          ),
          showRagScope && (
            <SearchConfigSelect
              key="scope"
              icon={{ category: "outlined", type: "hub" }}
              label={t("chatbot.composerSettings.scopeRowLabel")}
              title={t("chatbot.composerSettings.scopeTitle")}
              value={ragScope}
              options={ragScopes}
              open={openMenu === "scope"}
              onToggle={() => setOpenMenu((current) => (current === "scope" ? null : "scope"))}
              onChange={(value) => {
                onRagScopeChange(value);
                setOpenMenu(null);
              }}
            />
          ),
        ],
      ]}
    />
  );
}

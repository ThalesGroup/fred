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

import { useEffect, useMemo, useRef, useState } from "react";
import type { EffectiveChatOptions } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import type { SearchPolicyName } from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import styles from "./SearchConfig.module.css";

type RagScope = "corpus_only" | "hybrid" | "general_only";
type OpenMenu = "policy" | "scope" | null;

interface SearchConfigProps {
  onAttach: () => void;
  onRequestClose?: () => void;
  searchPolicy: SearchPolicyName;
  onSearchPolicyChange: (value: SearchPolicyName) => void;
  ragScope: RagScope;
  onRagScopeChange: (value: RagScope) => void;
  options?: EffectiveChatOptions | null;
}

interface SelectOption<T extends string> {
  value: T;
  label: string;
}

function SearchConfigSelect<T extends string>({
  title,
  value,
  options,
  open,
  onToggle,
  onChange,
}: {
  title: string;
  value: T;
  options: SelectOption<T>[];
  open: boolean;
  onToggle: () => void;
  onChange: (value: T) => void;
}) {
  const selected = options.find((option) => option.value === value) ?? options[0];

  return (
    <div className={styles.section}>
      <p className={styles.sectionLabel}>{title}</p>
      <div className={styles.selectWrap}>
        <button
          type="button"
          className={styles.selectTrigger}
          aria-haspopup="listbox"
          aria-expanded={open}
          onClick={onToggle}
        >
          <span className={styles.selectValue}>{selected.label}</span>
          <span className={`${styles.selectChevron} material-symbols-outlined`} aria-hidden>
            chevron_right
          </span>
        </button>

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
    </div>
  );
}

export function SearchConfig({
  onAttach,
  onRequestClose,
  searchPolicy,
  onSearchPolicyChange,
  ragScope,
  onRagScopeChange,
  options = null,
}: SearchConfigProps) {
  const [openMenu, setOpenMenu] = useState<OpenMenu>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  const showSearchPolicy = options?.search_policy_selection !== false;
  const showRagScope = options?.rag_scope_selection !== false;

  const searchPolicies = useMemo<SelectOption<SearchPolicyName>[]>(
    () => [
      { value: "strict", label: "Strict" },
      { value: "hybrid", label: "Hybride" },
      { value: "semantic", label: "Sémantique" },
    ],
    [],
  );

  const ragScopes = useMemo<SelectOption<RagScope>[]>(
    () => [
      { value: "corpus_only", label: "Corpus" },
      { value: "hybrid", label: "Corpus + web" },
      { value: "general_only", label: "Général" },
    ],
    [],
  );

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

  return (
    <div ref={rootRef} className={styles.card}>
      <button
        type="button"
        className={styles.attachButton}
        onClick={() => {
          onAttach();
          onRequestClose?.();
        }}
      >
        <span className={styles.attachBadge} aria-hidden>
          <span className="material-symbols-outlined">attach_file</span>
        </span>
        <span className={styles.attachLabel}>Ajouter un fichier</span>
        <span className={`${styles.attachIcon} material-symbols-outlined`} aria-hidden>
          add
        </span>
      </button>

      {showSearchPolicy && (
        <SearchConfigSelect
          title="Politique de recherche"
          value={searchPolicy}
          options={searchPolicies}
          open={openMenu === "policy"}
          onToggle={() => setOpenMenu((current) => (current === "policy" ? null : "policy"))}
          onChange={(value) => {
            onSearchPolicyChange(value);
            setOpenMenu(null);
          }}
        />
      )}

      {showRagScope && (
        <SearchConfigSelect
          title="Portée de recherche"
          value={ragScope}
          options={ragScopes}
          open={openMenu === "scope"}
          onToggle={() => setOpenMenu((current) => (current === "scope" ? null : "scope"))}
          onChange={(value) => {
            onRagScopeChange(value);
            setOpenMenu(null);
          }}
        />
      )}
    </div>
  );
}

// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useRef, useState, type ReactNode } from "react";
import Button from "@shared/atoms/Button/Button";
import Checkbox from "@shared/atoms/Checkbox/Checkbox";
import Icon, { type IconProps } from "@shared/atoms/Icon/Icon";
import SearchInput from "@shared/molecules/SearchInput/SearchInput";
import styles from "./SearchableCheckboxPicker.module.scss";

export interface CheckboxOption<T extends string> {
  value: T;
  label: string;
  content?: ReactNode;
  detail?: ReactNode;
}

type Labels = Record<
  | "title"
  | "reset"
  | "search"
  | "searchPlaceholder"
  | "clearSearch"
  | "selected"
  | "others"
  | "empty"
  | "cancel"
  | "apply",
  string
>;

export function groupCheckboxOptions<T extends CheckboxOption<string>>(
  options: T[],
  applied: readonly string[],
  search: string,
) {
  const query = search.trim().toLowerCase();
  const matches = options.filter((option) => option.label.toLowerCase().includes(query));
  const pinned = new Set(applied);
  return {
    selected: matches.filter((option) => pinned.has(option.value)),
    others: matches.filter((option) => !pinned.has(option.value)),
  };
}

export default function SearchableCheckboxPicker<T extends string>({
  icon,
  value,
  onChange,
  options,
  labels,
  triggerLabel,
  loading = false,
}: {
  icon: IconProps["type"];
  value: readonly T[];
  onChange: (next: T[]) => void;
  options: CheckboxOption<T>[];
  labels: Labels;
  triggerLabel: string;
  loading?: boolean;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [draft, setDraft] = useState<Set<T>>(new Set());
  const container = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);

  function close() {
    setIsOpen(false);
    trigger.current?.focus();
  }

  useEffect(() => {
    if (!isOpen) return;
    const dismissOutside = (event: Event) => {
      if (!container.current?.contains(event.target as Node)) setIsOpen(false);
    };
    document.addEventListener("mousedown", dismissOutside);
    document.addEventListener("focusin", dismissOutside);
    return () => {
      document.removeEventListener("mousedown", dismissOutside);
      document.removeEventListener("focusin", dismissOutside);
    };
  }, [isOpen]);

  function toggle(value: T) {
    setDraft((previous) => {
      const next = new Set(previous);
      if (next.has(value)) next.delete(value);
      else next.add(value);
      return next;
    });
  }

  function open() {
    setDraft(new Set(value));
    setSearch("");
    setIsOpen(true);
  }

  function apply() {
    onChange(options.map(({ value }) => value).filter((value) => draft.has(value)));
    close();
  }

  const { selected, others } = groupCheckboxOptions(options, value, search);
  const row = (option: CheckboxOption<T>) => (
    <label key={option.value} className={styles.row}>
      <Checkbox checked={draft.has(option.value)} onChange={() => toggle(option.value)} />
      <span className={styles.rowLabel}>{option.content ?? option.label}</span>
      {option.detail != null && <span className={styles.rowMeta}>{option.detail}</span>}
    </label>
  );

  return (
    <div
      className={styles.container}
      ref={container}
      data-open={isOpen}
      onKeyDown={(event) => {
        if (!isOpen || event.defaultPrevented || event.key !== "Escape") return;
        event.preventDefault();
        event.stopPropagation();
        close();
      }}
    >
      <button
        ref={trigger}
        type="button"
        className={styles.trigger}
        onClick={isOpen ? close : open}
        aria-haspopup="dialog"
        aria-expanded={isOpen}
        title={triggerLabel}
      >
        <Icon category="outlined" type={icon} />
        <span className={styles.label}>{triggerLabel}</span>
        <Icon category="outlined" type="arrow_drop_down" />
      </button>
      {isOpen && (
        <div className={styles.panel} role="dialog" aria-label={labels.title}>
          <SearchInput
            value={search}
            onChange={setSearch}
            placeholder={labels.searchPlaceholder}
            ariaLabel={labels.search}
            clearAriaLabel={labels.clearSearch}
            size="xs"
            autoFocus
          />
          <label className={`${styles.row} ${styles.platformRow}`}>
            <Checkbox checked={draft.size === 0} onChange={() => setDraft(new Set())} />
            <span className={styles.rowLabel}>{labels.reset}</span>
          </label>
          <div className={styles.separator} />
          <div className={styles.list}>
            {selected.length > 0 && <span className={styles.groupLabel}>{labels.selected}</span>}
            {selected.map(row)}
            {selected.length > 0 && others.length > 0 && <span className={styles.groupLabel}>{labels.others}</span>}
            {others.map(row)}
            {selected.length + others.length === 0 && <p className={styles.empty}>{labels.empty}</p>}
          </div>
          <div className={styles.footer}>
            <Button variant="text" color="primary" size="small" onClick={close}>
              {labels.cancel}
            </Button>
            <Button variant="filled" color="primary" size="small" onClick={apply} disabled={loading}>
              {labels.apply}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

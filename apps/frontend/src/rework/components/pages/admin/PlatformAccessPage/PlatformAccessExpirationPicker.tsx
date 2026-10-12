// SPDX-License-Identifier: Apache-2.0
import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import DateTimeInput from "@shared/atoms/DateTimeInput/DateTimeInput";
import Icon from "@shared/atoms/Icon/Icon";
import rangeStyles from "@shared/molecules/TimeRangeSelector/TimeRangeSelector.module.scss";
import styles from "./PlatformAccessPage.module.css";

const localDate = (date: Date) => {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
};

export default function PlatformAccessExpirationPicker({
  value,
  disabled,
  onChange,
  onOpenChange,
}: {
  value: string;
  disabled: boolean;
  onChange: (value: string) => void;
  onOpenChange: (open: boolean) => void;
}) {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(value);
  const container = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const panelId = useId();
  const errorId = useId();
  const valid = draft !== "" && Number.isFinite(new Date(draft).getTime()) && new Date(draft).getTime() > Date.now();
  const close = () => {
    setOpen(false);
    onOpenChange(false);
  };
  const apply = (next: string) => {
    onChange(next);
    close();
    trigger.current?.focus();
  };
  useEffect(() => {
    if (!open) return;
    const outside = (event: MouseEvent) => {
      if (!container.current?.contains(event.target as Node)) {
        setOpen(false);
        onOpenChange(false);
      }
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || !container.current?.closest('[role="dialog"]')?.contains(event.target as Node))
        return;
      event.preventDefault();
      event.stopPropagation();
      setOpen(false);
      onOpenChange(false);
      trigger.current?.focus();
    };
    document.addEventListener("mousedown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [open, onOpenChange]);

  return (
    <div ref={container} className={`${rangeStyles.container} ${styles.expirationPicker}`} data-open={open}>
      <span id={`${panelId}-label`}>{t("rework.platformAccess.links.expiry")}</span>
      <button
        ref={trigger}
        type="button"
        className={rangeStyles.trigger}
        aria-labelledby={`${panelId}-label ${panelId}-value`}
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        disabled={disabled}
        onClick={() => {
          if (open) close();
          else {
            setDraft(value || localDate(new Date(Date.now() + 7 * 86400000)));
            setOpen(true);
            onOpenChange(true);
          }
        }}
      >
        <span className={`${rangeStyles.triggerInner} ${styles.expirationTrigger}`}>
          <Icon category="outlined" type="schedule" />
          <span id={`${panelId}-value`}>
            {value ? new Date(value).toLocaleString(i18n.language) : t("rework.platformAccess.links.never")}
          </span>
          <Icon category="outlined" type="arrow_drop_down" />
        </span>
      </button>
      {open && (
        <div id={panelId} className={`${rangeStyles.dropdown} ${styles.expirationPanel}`}>
          <div className={`${rangeStyles.dropdownTop} ${styles.expirationOptions}`}>
            <div className={rangeStyles.customPanel}>
              <DateTimeInput
                label={t("rework.platformAccess.links.expiryDate")}
                value={draft}
                min={localDate(new Date())}
                autoFocus
                disabled={disabled}
                onChange={(event) => setDraft(event.target.value)}
                aria-invalid={!valid || undefined}
                aria-describedby={!valid ? errorId : undefined}
              />
              {!valid && (
                <p id={errorId} role="alert">
                  {t("rework.platformAccess.links.futureExpiry")}
                </p>
              )}
              <Button
                color="primary"
                variant="filled"
                size="medium"
                disabled={disabled || !valid}
                onClick={() => apply(draft)}
              >
                {t("rework.analytics.timeRange.apply")}
              </Button>
            </div>
            <div className={rangeStyles.divider} />
            <div className={rangeStyles.presets}>
              {[1, 7, 30].map((days) => (
                <button
                  type="button"
                  key={days}
                  className={rangeStyles.presetItem}
                  disabled={disabled}
                  onClick={() => apply(localDate(new Date(Date.now() + days * 86400000)))}
                >
                  {t(`rework.platformAccess.links.expiryPresets.days${days}`)}
                </button>
              ))}
              <button type="button" className={rangeStyles.presetItem} disabled={disabled} onClick={() => apply("")}>
                {t("rework.platformAccess.links.never")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Copyright Thales 2026
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy at http://www.apache.org/licenses/LICENSE-2.0

import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon";
import styles from "./SkillBadge.module.css";

interface SkillBadgeProps {
  name: string;
  description?: string | null;
  onOpen?: (name: string) => void;
}

export function SkillBadge({ name, description, onOpen }: SkillBadgeProps) {
  const { t } = useTranslation();
  const hint = [t("chatbot.skills.platformProvided"), description?.trim()].filter(Boolean).join("\n");
  const content = (
    <>
      <Icon category="outlined" type="customPlatformSkill" />
      <span className={styles.name} data-skill-name={name}>
        {name}
      </span>
    </>
  );
  if (onOpen) {
    return (
      <button
        type="button"
        className={`${styles.badge} ${styles.action}`}
        onClick={() => onOpen(name)}
        aria-label={t("chatbot.skills.open", { name })}
        title={hint}
      >
        {content}
      </button>
    );
  }
  return (
    <span className={styles.badge} role="group" aria-label={t("chatbot.skills.badge", { name })} title={hint}>
      {content}
    </span>
  );
}

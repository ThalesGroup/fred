// Copyright Thales 2026
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy at http://www.apache.org/licenses/LICENSE-2.0

import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon";
import { skillPresentation, skillTooltip } from "@rework/utils/skillPresentation";
import styles from "./SkillBadge.module.css";

interface SkillBadgeProps {
  name: string;
  description?: string | null;
  builtin?: boolean;
  onOpen?: (name: string) => void;
}

export function SkillBadge({ name, description, builtin, onOpen }: SkillBadgeProps) {
  const { t } = useTranslation();
  const display = skillPresentation(t, { name, description, builtin });
  const hint = skillTooltip(display.title, display.description);
  const content = (
    <>
      <Icon category="outlined" type="customPlatformSkill" />
      <span className={styles.name} data-skill-name={name}>
        {display.title}
      </span>
    </>
  );
  if (onOpen) {
    return (
      <button
        type="button"
        className={`${styles.badge} ${styles.action}`}
        data-kind="skill"
        data-surface="bubble"
        onClick={() => onOpen(name)}
        aria-label={t("chatbot.skills.open", { name: display.title })}
        title={hint}
      >
        {content}
      </button>
    );
  }
  return (
    <span
      className={styles.badge}
      data-kind="skill"
      data-surface="bubble"
      role="group"
      aria-label={t("chatbot.skills.badge", { name: display.title })}
      title={hint}
    >
      {content}
    </span>
  );
}

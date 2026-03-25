import { IconCategory, IconType } from "@shared/utils/Type.ts";
import styles from "./Icon.module.scss";

export interface IconProps {
  category: IconCategory;
  type: IconType;
  filled?: boolean;
}

export default function Icon({ category, type, filled }: IconProps) {
  const classes = `material-symbols-${category} ${styles.icon} ${filled ? styles.filled : ""}`;
  return <span className={classes}>{type}</span>;
}

import { IconCategory, IconType, isCustomIcon } from "@shared/utils/Type.ts";
import styles from "./Icon.module.scss";

export interface IconProps {
  category: IconCategory;
  type: IconType;
  filled?: boolean;
}

export default function Icon({ category, type, filled }: IconProps) {
  if (isCustomIcon(type)) {
    const iconPath = `/images/icons/${type}.svg`;

    return (
      <span
        className={`${styles.icon} ${styles.customIcon}`}
        style={{
          maskImage: `url(${iconPath})`,
          WebkitMaskImage: `url(${iconPath})`,
        }}
        aria-label={`${type} icon`}
      />
    );
  }

  const classes = `material-symbols-${category} ${styles.icon} ${filled ? styles.filled : ""}`;
  return <span className={classes}>{type}</span>;
}

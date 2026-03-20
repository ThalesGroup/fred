import styles from "./Breadcrumb.module.css";
import React from "react";
import KeyboardArrowRightIcon from "@mui/icons-material/KeyboardArrowRight";

interface BreadcrumbProps {
  items: BreadcrumbItemProps[];
}

interface BreadcrumbItemProps {
  label: string;
  callback?: () => void;
  separatorIcon?: React.ReactNode;
}

export default function Breadcrumb({ items }: BreadcrumbProps) {
  return (
    <div className={styles.breadcrumb}>
      {items.map((item, index) => (
        <>
          <span key={index}>{item.label}</span>
          {item.separatorIcon || <KeyboardArrowRightIcon />}
        </>
      ))}
    </div>
  );
}

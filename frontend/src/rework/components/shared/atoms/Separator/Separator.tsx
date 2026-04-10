import styles from "./Separator.module.scss";
import React from "react";

interface SeparatorProps {
  margin?: string;
}

export default function Separator({ margin }: SeparatorProps) {
  return <div className={styles["separator"]} style={{ "--separator-margin": margin } as React.CSSProperties}></div>;
}

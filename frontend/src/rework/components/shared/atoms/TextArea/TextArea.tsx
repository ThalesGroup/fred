import { ComponentPropsWithoutRef } from "react";
import styles from "./TextArea.module.scss";

export interface TextInputProps extends ComponentPropsWithoutRef<"textarea"> {
    error?: boolean;
}

export default function TextArea({ error, ...props }: TextInputProps) {
  return <textarea className={`${styles["text-area"]} ${error ? styles.error : ""}`} {...props}></textarea>;
}

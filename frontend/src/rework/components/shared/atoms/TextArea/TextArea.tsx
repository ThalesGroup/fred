import { ComponentPropsWithRef, useId } from "react";
import styles from "./TextArea.module.scss";

export interface TextAreaProps extends ComponentPropsWithRef<"textarea"> {
  label: string;
  explanation?: string;
  error?: string;
}

export default function TextArea({ label,explanation, error, maxLength, value, required, ...props }: TextAreaProps) {
  const id = useId();
  const characterCounter = String(value).length;

  return (
    <div
      className={`${styles.input} ${props.disabled ? styles.disabled : ""} ${!props.disabled && error ? styles.error : ""}`}
    >
      <label className={styles.label} htmlFor={id}>
        {required ? `${label} *` : label}
      </label>

      <textarea id={id} value={value} maxLength={maxLength} required={required} {...props} />

      <span className={styles.information}>
        <span className={styles.hint}>{error || explanation || null}</span>
        <span className={styles.maxLength}>{maxLength && `${characterCounter} / ${maxLength}`}</span>
      </span>
    </div>
  );
}

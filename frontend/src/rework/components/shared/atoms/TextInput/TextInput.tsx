import styles from "./TextInput.module.scss";
import { ComponentPropsWithoutRef, useId } from "react";

export interface TextInputProps extends ComponentPropsWithoutRef<"input"> {
  label: string;
  placeholder: string;
  explication?: string;
  error?: string;
}

export default function TextInput({ label, placeholder, explication, error, ...props }: TextInputProps) {
  const id = useId();

  return (
    <div className={`${styles.input} ${props.disabled ? styles.disabled : ""} ${(!props.disabled && error) ? styles.error : ""}`}>
      <label className={styles.label} htmlFor={id}>
        {label}
      </label>
      <input id={id} type={"text"} placeholder={placeholder} {...props} />
      <span className={styles.hint}>{error || explication || null}</span>
    </div>
  );
}

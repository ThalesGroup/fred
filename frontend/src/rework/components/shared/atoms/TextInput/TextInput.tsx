import styles from "./TextInput.module.scss";
import { ComponentPropsWithRef, useId } from "react";
import Icon, { IconProps } from "@shared/atoms/Icon/Icon.tsx";

export interface TextInputProps extends ComponentPropsWithRef<"input"> {
  label?: string;
  explanation?: string;
  error?: string;
  icon?: IconProps;
  compact?: boolean;
}

export default function TextInput({
  label,
  explanation,
  error,
  icon,
  compact = false,
  maxLength,
  value,
  required,
  ...props
}: TextInputProps) {
  const id = useId();

  const characterCounter = String(value).length;

  return (
    <div
      className={`${styles.input} ${props.disabled ? styles.disabled : ""} ${!props.disabled && error ? styles.error : ""}`}
      data-compact={compact}
    >
      {label && (
        <label className={styles.label} htmlFor={id}>
          {required ? `${label} *` : label}
        </label>
      )}
      {icon && (
        <span className={styles.icon}>
          <Icon {...icon} />
        </span>
      )}
      <input
        id={id}
        type={"text"}
        value={value}
        maxLength={maxLength}
        required={required}
        autoComplete="off"
        {...props}
      />
      <span className={styles.information}>
        <span className={styles.hint}>{error || explanation || null}</span>
        <span className={styles.maxLength}>{maxLength && `${characterCounter} / ${maxLength}`}</span>
      </span>
    </div>
  );
}

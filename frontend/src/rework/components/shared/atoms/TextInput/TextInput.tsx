import styles from "./TextInput.module.scss";
import { ComponentPropsWithRef, useId } from "react";
import Icon, { IconProps } from "@shared/atoms/Icon/Icon.tsx";

export interface TextInputProps extends ComponentPropsWithRef<"input"> {
  label?: string;
  placeholder: string;
  explication?: string;
  error?: string;
  icon?: IconProps;
  compact?: boolean;
}

export default function TextInput({
  label,
  placeholder,
  explication,
  error,
  icon,
  compact = false,
  ref,
  ...props
}: TextInputProps) {
  const id = useId();

  return (
    <div
      className={`${styles.input} ${props.disabled ? styles.disabled : ""} ${!props.disabled && error ? styles.error : ""}`}
      data-compact={compact}
    >
      {label && (
        <label className={styles.label} htmlFor={id}>
          {label}
        </label>
      )}
      {icon && (
        <span className={styles.icon}>
          <Icon {...icon} />
        </span>
      )}
      <input ref={ref} id={id} type={"text"} placeholder={placeholder} {...props} />
      <span className={styles.hint}>{error || explication || null}</span>
    </div>
  );
}

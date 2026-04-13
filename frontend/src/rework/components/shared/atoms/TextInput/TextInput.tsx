import styles from "./TextInput.module.scss";
import { ChangeEvent, ComponentPropsWithRef, useId, useState } from "react";
import Icon, { IconProps } from "@shared/atoms/Icon/Icon.tsx";

export interface TextInputProps extends ComponentPropsWithRef<"input"> {
  label?: string;
  placeholder: string;
  explication?: string;
  error?: string;
  icon?: IconProps;
  compact?: boolean;
  maxLength?: number;
  required?: boolean;
}

export default function TextInput({
  label,
  placeholder,
  explication,
  error,
  icon,
  compact = false,
  onChange,
  maxLength = 0,
  value,
  defaultValue,
  required = false,
  ref,
  ...props
}: TextInputProps) {
  const id = useId();

  const initialValue = value ?? defaultValue ?? "";
  const [characterCounter, setCharacterCounter] = useState(String(initialValue).length);

  const handleChange = (e: ChangeEvent<HTMLInputElement>) => {
    if (maxLength && e.target.value.length > maxLength) {
      e.target.value = e.target.value.slice(0, maxLength);
    }

    setCharacterCounter(e.target.value.length);

    if (onChange) onChange(e);
  };

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
        ref={ref}
        id={id}
        type={"text"}
        placeholder={placeholder}
        onChange={handleChange}
        value={value}
        defaultValue={defaultValue}
        {...props}
      />
      <span className={styles.hint}>
        {error || explication || (maxLength !== 0 && `${characterCounter} / ${maxLength}`) || null}
      </span>
    </div>
  );
}

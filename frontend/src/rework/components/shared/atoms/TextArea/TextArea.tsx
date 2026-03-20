import { ChangeEvent, ComponentPropsWithRef, useEffect, useId, useState } from "react";
import styles from "./TextArea.module.scss";

export interface TextAreaProps extends ComponentPropsWithRef<"textarea"> {
  label: string;
  placeholder: string;
  explication?: string;
  error?: string;
  maxLength?: number;
}

export default function TextArea({
  label,
  placeholder,
  explication,
  error,
  maxLength = 0,
  onChange,
  value,
  defaultValue,
  ref,
  ...props
}: TextAreaProps) {
  const id = useId();

  const initialValue = value ?? defaultValue ?? "";
  const [characterCounter, setCharacterCounter] = useState(String(initialValue).length);

  useEffect(() => {
    const currentVal = value ?? defaultValue ?? "";
    setCharacterCounter(String(currentVal).length);
  }, [value, defaultValue]);

  const handleChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    if (maxLength && e.target.value.length > maxLength) {
      e.target.value = e.target.value.slice(0, maxLength);
    }

    setCharacterCounter(e.target.value.length);

    if (onChange) onChange(e);
  };

  return (
    <div
      className={`${styles.input} ${props.disabled ? styles.disabled : ""} ${!props.disabled && error ? styles.error : ""}`}
    >
      <label className={styles.label} htmlFor={id}>
        {label}
      </label>

      <textarea
        ref={ref}
        id={id}
        placeholder={placeholder}
        onChange={handleChange}
        maxLength={maxLength > 0 ? maxLength : undefined}
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

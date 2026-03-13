import styles from "./TextInput.module.css";
import { ComponentPropsWithoutRef, useId } from "react";

export interface TextInputProps extends ComponentPropsWithoutRef<"input"> {
  label: string;
  placeholder: string;
  explication?: string;
  error?: string;
}

export default function TextInput({ label, placeholder, explication, error }: TextInputProps) {
  const id = useId();

  return (
    <div className={styles.input}>
      <label className="label-large" htmlFor={id}>
        {label}
      </label>
      <input id={id} type={"text"} placeholder={placeholder} />
      <span className="title-small">{error || explication || null}</span>
    </div>
  );
}

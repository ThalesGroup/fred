import styles from "./Switch.module.css";
import { ComponentPropsWithRef } from "react";

interface SwitchProps extends ComponentPropsWithRef<"input"> {}

export default function Switch({ ref, ...rest }: SwitchProps) {
  return (
    <label className={styles.switchContainer}>
      <input type="checkbox" ref={ref} className={styles.nativeInput} {...rest} />
      <div className={styles.switch}>
        <div className={styles.stateLayer}>
          <div className={styles.switchHandle}></div>
        </div>
      </div>
    </label>
  );
}

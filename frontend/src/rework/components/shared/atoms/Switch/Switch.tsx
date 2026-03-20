import styles from "./Switch.module.scss";
import { ComponentPropsWithRef } from "react";

interface SwitchProps extends ComponentPropsWithRef<"input"> {}

export default function Switch({ ref, ...rest }: SwitchProps) {
  return (
    <label className={styles["switch-container"]}>
      <input type="checkbox" ref={ref} className={styles["native-input"]} {...rest} />
      <div className={styles["switch"]}>
        <div className={styles["state-layer"]}>
          <div className={styles["switch-handle"]}></div>
        </div>
      </div>
    </label>
  );
}

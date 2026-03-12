import styles from "./Switch.module.scss";
import { forwardRef, InputHTMLAttributes } from "react";

interface SwitchProps extends InputHTMLAttributes<HTMLInputElement> {}

const Switch = forwardRef<HTMLInputElement, SwitchProps>(({ className, ...rest }, ref) => {
  return (
    <label className={styles["switch-container"]}>
      <input
        type="checkbox"
        ref={ref}
        className={styles["native-input"]}
        {...rest}
      />
      <div
        className={styles["switch"]}
      >
        <div className={styles["state-layer"]}>
          <div className={styles["switch-handle"]}></div>
        </div>
      </div>
    </label>
  );
});

Switch.displayName = "Switch";

export default Switch;

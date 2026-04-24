import Switch from "@components/shared/atoms/Switch/Switch";
import styles from "./SwitchRow.module.css";

export interface SwitchRowProps {
  label: string;
  description: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}

export function SwitchRow({ label, description, checked, onChange }: SwitchRowProps) {
  return (
    <label className={styles.switchRow}>
      <div className={styles.text}>
        <span className={styles.label}>{label}</span>
        <span className={styles.description}>{description}</span>
      </div>
      <Switch checked={checked} onChange={(e) => onChange(e.target.checked)} />
    </label>
  );
}

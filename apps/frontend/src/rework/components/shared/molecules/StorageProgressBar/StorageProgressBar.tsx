// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import ProgressBar from "@shared/atoms/ProgressBar/ProgressBar.tsx";
import { ColorTheme } from "../../utils/Type.ts";
import styles from "./StorageProgressBar.module.css";

interface StorageProgressBarProps {
  currentBytes: number;
  maxBytes: number;
  theme: ColorTheme;
}

export function formatBytes(bytes: number): string {
  if (bytes <= 0) return "0 octet";
  const k = 1024;
  const sizes = ["octets", "Ko", "Mo", "Go", "To"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  const val = bytes / Math.pow(k, i);
  const formatted = val % 1 === 0 ? val.toFixed(0) : val.toFixed(1);
  return `${formatted} ${sizes[i]}`;
}

export default function StorageProgressBar({ currentBytes, maxBytes, theme }: StorageProgressBarProps) {
  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <span className={styles.label}>
          {formatBytes(currentBytes)} / {formatBytes(maxBytes)}
        </span>
      </div>
      <ProgressBar theme={theme} current={currentBytes} max={maxBytes} />
    </div>
  );
}

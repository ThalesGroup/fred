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

import React from "react";
import { ColorTheme } from "../../utils/Type.ts";
import styles from "./ProgressBar.module.css";

interface ProgressBarProps {
  theme: ColorTheme;
  current: number;
  max: number;
}

export default function ProgressBar({ theme, current, max }: ProgressBarProps) {
  const percentage = max > 0 ? Math.min(100, Math.max(0, (current / max) * 100)) : 0;

  return (
    <div className={styles.track} role="progressbar" aria-valuenow={current} aria-valuemin={0} aria-valuemax={max}>
      <div data-color={theme} className={styles.fill} style={{ width: `${percentage}%` }} />
    </div>
  );
}

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

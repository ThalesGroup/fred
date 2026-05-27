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
import Icon from "@shared/atoms/Icon/Icon.tsx";
import styles from "./Breadcrumb.module.css";

interface BreadcrumbProps {
  items: BreadcrumbItemProps[];
}

interface BreadcrumbItemProps {
  label: string;
  callback?: () => void;
  separatorIcon?: React.ReactNode;
}

export default function Breadcrumb({ items }: BreadcrumbProps) {
  return (
    <div className={styles.breadcrumb}>
      {items.map((item, index) => (
        <React.Fragment key={index}>
          <span>{item.label}</span>
          {item.separatorIcon ?? <Icon category="outlined" type="chevron_right" />}
        </React.Fragment>
      ))}
    </div>
  );
}

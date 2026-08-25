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

import styles from "./NavPanelHeader.module.scss";

interface NavPanelHeaderProps {
  title: string;
}

/**
 * Shared title row for the mainNavPanel's top-level sections (Home,
 * Marketplace, …) — one identical header so the panels never drift apart
 * visually as they're edited independently.
 */
export default function NavPanelHeader({ title }: NavPanelHeaderProps) {
  return <div className={styles.header}>{title}</div>;
}

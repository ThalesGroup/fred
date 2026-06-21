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

import { ReactNode, useState } from "react";
import { Collapse } from "@mui/material";
import Icon, { IconProps } from "@shared/atoms/Icon/Icon.tsx";
import styles from "./WorkspaceRoot.module.css";

interface WorkspaceRootAction {
  icon: IconProps;
  label: string;
  onClick: () => void;
}

interface WorkspaceRootProps {
  /** Distinctive icon for this root (database / person / groups). */
  icon: IconProps;
  title: string;
  /** Right-aligned nature marker (badge, "privé · dans X", file count…). */
  meta?: ReactNode;
  defaultOpen?: boolean;
  /** Action revealed on hover of this root (e.g. "+ files" / "+ folder"). */
  action?: WorkspaceRootAction;
  children: ReactNode;
}

/**
 * One root branch of the unified workspace tree (FILES-04).
 *
 * Renders a distinctive, collapsible root row (chevron + icon + title + nature marker, plus
 * a hover action) over an expandable body. The three roots — Resources (indexed corpus),
 * Mon espace (personal-in-team), Espace d'équipe (team-shared) — live together in one tree.
 */
export default function WorkspaceRoot({
  icon,
  title,
  meta,
  defaultOpen = false,
  action,
  children,
}: WorkspaceRootProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className={styles.root}>
      <div className={styles.headerRow}>
        <button type="button" className={styles.header} onClick={() => setOpen((value) => !value)} aria-expanded={open}>
          <span className={styles.chevron}>
            <Icon category="outlined" type={open ? "expand_more" : "chevron_right"} />
          </span>
          <span className={styles.icon}>
            <Icon {...icon} />
          </span>
          <span className={styles.title}>{title}</span>
        </button>
        {meta != null && <span className={styles.meta}>{meta}</span>}
        {action && (
          <button type="button" className={styles.action} onClick={action.onClick} aria-label={action.label}>
            <Icon {...action.icon} />
          </button>
        )}
      </div>
      <Collapse in={open} unmountOnExit>
        <div className={styles.body}>{children}</div>
      </Collapse>
    </div>
  );
}

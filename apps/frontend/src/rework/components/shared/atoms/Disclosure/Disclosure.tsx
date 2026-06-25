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

import { PropsWithChildren, useState } from "react";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import styles from "./Disclosure.module.css";

interface DisclosureProps {
  title: string;
  defaultOpen?: boolean;
}

/** A lightweight collapsible section (replaces MUI Accordion). Design-tokens only. */
export default function Disclosure({ title, defaultOpen = false, children }: PropsWithChildren<DisclosureProps>) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className={styles.disclosure}>
      <button type="button" className={styles.summary} aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <span className={styles.title}>{title}</span>
        <Icon category="outlined" type={open ? "expand_less" : "expand_more"} />
      </button>
      {open && <div className={styles.content}>{children}</div>}
    </div>
  );
}

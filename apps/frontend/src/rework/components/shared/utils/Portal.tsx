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

import { useEffect, useState, ReactNode } from "react";
import { createPortal } from "react-dom";

const portalOwners = new WeakMap<HTMLElement, { count: number; created: boolean }>();

/** Prefer the originating consumer-owned theme root; legacy FRED callers retain body portals. */
export function uiPortalRoot(anchor: Element | null): HTMLElement {
  return (anchor?.closest(".fred-ui") as HTMLElement | null) ?? document.body;
}

interface PortalProps {
  children: ReactNode;
  id?: string;
  root?: HTMLElement | null;
}

export const Portal = ({ children, id = "portal-root", root }: PortalProps) => {
  const [container, setContainer] = useState<HTMLElement | null>(null);

  useEffect(() => {
    const host = root ?? document.body;
    let portalElement = [...host.children].find((child) => child.id === id) as HTMLElement | undefined;
    let created = false;

    if (!portalElement) {
      portalElement = document.createElement("div");
      portalElement.id = id;
      portalElement.setAttribute("data-portal-container", "true");
      host.appendChild(portalElement);
      created = true;
    }

    const ownership = portalOwners.get(portalElement) ?? { count: 0, created };
    ownership.count += 1;
    portalOwners.set(portalElement, ownership);

    setContainer(portalElement);

    return () => {
      ownership.count -= 1;
      if (ownership.count === 0) {
        portalOwners.delete(portalElement);
        if (ownership.created && portalElement.parentNode) portalElement.remove();
      }
    };
  }, [id, root]);

  if (!container) return null;

  return createPortal(children, container);
};

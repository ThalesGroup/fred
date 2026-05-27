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

interface PortalProps {
  children: ReactNode;
  id?: string;
}

export const Portal = ({ children, id = "portal-root" }: PortalProps) => {
  const [container, setContainer] = useState<HTMLElement | null>(null);

  useEffect(() => {
    let portalElement = document.getElementById(id);
    let created = false;

    if (!portalElement) {
      portalElement = document.createElement("div");
      portalElement.id = id;
      portalElement.setAttribute("data-portal-container", "true");
      document.body.appendChild(portalElement);
      created = true;
    }

    setContainer(portalElement);

    return () => {
      if (created && portalElement?.parentNode) {
        portalElement.parentNode.removeChild(portalElement);
      }
    };
  }, [id]);

  if (!container) return null;

  return createPortal(children, container);
};

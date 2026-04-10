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

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

import { PropsWithChildren, useCallback, useEffect, useRef, useState } from "react";
import styles from "./HorizontalScrollRow.module.css";

interface HorizontalScrollRowProps {
  gap?: string;
  className?: string;
}

export function HorizontalScrollRow({
  gap,
  className,
  children,
}: PropsWithChildren<HorizontalScrollRowProps>) {
  const rowRef = useRef<HTMLDivElement>(null);
  const [fadeLeft, setFadeLeft] = useState(false);
  const [fadeRight, setFadeRight] = useState(false);

  const scrollByPage = useCallback((direction: "left" | "right") => {
    const el = rowRef.current;
    if (!el) return;
    const delta = Math.max(180, Math.round(el.clientWidth * 0.85));
    const left = direction === "left" ? -delta : delta;
    el.scrollBy({ left, behavior: "smooth" });
  }, []);

  useEffect(() => {
    const el = rowRef.current;
    if (!el) return;

    const update = () => {
      setFadeLeft(el.scrollLeft > 0);
      setFadeRight(el.scrollLeft + el.clientWidth < el.scrollWidth - 1);
    };

    update();
    el.addEventListener("scroll", update, { passive: true });
    const ro = new ResizeObserver(update);
    ro.observe(el);

    return () => {
      el.removeEventListener("scroll", update);
      ro.disconnect();
    };
  }, []);

  return (
    <div
      className={`${styles.wrapper} ${className ?? ""}`}
      data-fade-left={fadeLeft}
      data-fade-right={fadeRight}
    >
      {fadeLeft && (
        <button
          type="button"
          className={`${styles.arrowBtn} ${styles.arrowLeft}`}
          onClick={() => scrollByPage("left")}
          aria-label="Scroll left"
        >
          ‹
        </button>
      )}
      <div
        ref={rowRef}
        className={styles.row}
        style={gap ? ({ "--row-gap": gap } as React.CSSProperties) : undefined}
      >
        {children}
      </div>
      {fadeRight && (
        <button
          type="button"
          className={`${styles.arrowBtn} ${styles.arrowRight}`}
          onClick={() => scrollByPage("right")}
          aria-label="Scroll right"
        >
          ›
        </button>
      )}
    </div>
  );
}

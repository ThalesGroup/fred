// Copyright Thales 2026
// Licensed under the Apache License, Version 2.0.

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { KeyCloakService } from "../../../../../security/KeycloakService";
import type { ContentNotice } from "../../../../../slices/runtime/runtimeOpenApi";
import styles from "./ContentPolicyNotice.module.css";

const POLL_INTERVALS_MS = [1800, 2500, 3500, 5500, 8500, 13000];

function lookupUrl(messagesUrl: string | null | undefined, supportErrorRef: string | null | undefined, rank: number) {
  if (
    !messagesUrl ||
    !supportErrorRef ||
    !/^[0-9a-f]{32}$/.test(supportErrorRef) ||
    !Number.isInteger(rank) ||
    rank < 0
  )
    return null;
  if (!URL.canParse(messagesUrl, window.location.origin)) return null;
  const url = new URL(messagesUrl, window.location.origin);
  if (url.origin !== window.location.origin || !url.pathname.endsWith("/messages")) return null;
  url.pathname = url.pathname.replace(/\/messages$/, `/content-notices/${rank}/${supportErrorRef}`);
  url.search = "";
  url.hash = "";
  return url.toString();
}

export function ContentPolicyNotice({
  notice,
  messagesUrl,
  supportErrorRef,
  rank,
  timestamp,
}: {
  notice: ContentNotice;
  messagesUrl?: string | null;
  supportErrorRef?: string | null;
  rank: number;
  timestamp: string;
}) {
  const { t } = useTranslation();
  const card = useRef<HTMLElement>(null);
  const [visible, setVisible] = useState(typeof IntersectionObserver === "undefined");
  const [enriched, setEnriched] = useState<{ url: string; notice: ContentNotice }>();
  const url = lookupUrl(messagesUrl, supportErrorRef, rank);
  const result = url !== null && enriched?.url === url ? enriched.notice : undefined;
  const pending = notice.analysis_state === "pending" && result === undefined;
  const explanation = notice.analysis_state === "pending" ? result?.explanation : notice.explanation;
  useEffect(() => {
    if (!pending || !card.current || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting));
    observer.observe(card.current);
    return () => observer.disconnect();
  }, [pending]);
  useEffect(() => {
    if (!url || !pending || !visible || Date.now() - Date.parse(timestamp) >= 90_000) return;
    const controller = new AbortController();
    let attempt = 0;
    let timer: ReturnType<typeof setTimeout>;
    const schedule = () => {
      const delay = POLL_INTERVALS_MS[attempt++];
      if (delay !== undefined && !controller.signal.aborted) timer = setTimeout(poll, delay);
    };
    const poll = async () => {
      try {
        await KeyCloakService.ensureFreshToken(30);
        if (controller.signal.aborted) return;
        const response = await fetch(url, {
          headers: { Authorization: `Bearer ${KeyCloakService.GetToken() ?? ""}` },
          signal: controller.signal,
          redirect: "error",
        });
        if (response.status === 401 || response.status === 403) return;
        if (response.ok) {
          const updated = (await response.json()) as ContentNotice | null;
          if (controller.signal.aborted) return;
          if (updated?.code === "content_policy_blocked" && updated.analysis_state !== "pending") {
            setEnriched({ url, notice: updated });
            return;
          }
        }
      } catch {
        // Keep the base notice while the optional result is unavailable.
      }
      schedule();
    };
    schedule();
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [pending, timestamp, url, visible]);
  const message = `rework.contentPolicy.${notice.kind}` as const;
  const categories = notice.categories ?? [];
  const categoryNames = categories.map((category) => t(`rework.contentPolicy.categories.${category}`)).join(", ");
  return (
    <section className={styles.notice} ref={card} role="alert">
      <h2>{t(`${message}.title`)}</h2>
      <p>{t(notice.origin === "tool" ? "rework.contentPolicy.toolDescription" : `${message}.description`)}</p>
      {notice.kind !== "model_refusal" && <p>{t(`rework.contentPolicy.origin.${notice.origin ?? "unknown"}`)}</p>}
      {categoryNames && <p>{t("rework.contentPolicy.filters", { categories: categoryNames })}</p>}
      {explanation && (
        <p>
          {t("rework.contentPolicy.explanation", {
            category: t(`rework.contentPolicy.categories.${explanation}`),
          })}
        </p>
      )}
    </section>
  );
}

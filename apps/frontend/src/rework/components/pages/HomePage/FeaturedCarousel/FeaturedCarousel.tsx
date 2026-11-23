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

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import { resolveAgentIcon } from "@shared/utils/agentIcon.ts";
import { useFrontendProperties } from "../../../../../hooks/useFrontendProperties.ts";
import type { FeaturedHomeAgent } from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import AgentChatButton from "@shared/organisms/AgentCard/AgentChatButton.tsx";
import SectionMarker from "../SectionMarker/SectionMarker.tsx";
import styles from "./FeaturedCarousel.module.scss";

export const AUTOPLAY_MS = 7000;

interface FeaturedCarouselProps {
  featured: FeaturedHomeAgent[];
  teamName: (teamId: string) => string | undefined;
}

const prefersReducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;

/** Admin-ordered "featured" agents of the advanced home, one at a time. */
export default function FeaturedCarousel({ featured, teamName }: FeaturedCarouselProps) {
  const { t } = useTranslation();
  const { agentIconName } = useFrontendProperties();
  // Track index: 0 and count + 1 are edge copies, so wrapping keeps sliding the same way.
  const [slot, setSlot] = useState(1);
  // Set for one frame while jumping from an edge copy to its real twin, without animation.
  const [instant, setInstant] = useState(false);
  const trackRef = useRef<HTMLDivElement>(null);
  // Auto-rotation is opt-out by the user (pause button) and off for reduced motion.
  const [playing, setPlaying] = useState(() => !prefersReducedMotion());
  // Hover or keyboard focus inside the banner holds it without changing `playing`.
  const [held, setHeld] = useState(false);
  const count = featured.length;
  const loop = count > 1;
  // The list can shrink on refetch (an agent was disabled): stay in range.
  const trackPos = loop ? Math.min(Math.max(slot, 0), count + 1) : 0;
  const position = loop ? (trackPos - 1 + count) % count : 0;
  const current = featured[position];
  // An edge copy maps to its real twin; also covers a missed transitionend (reduced motion).
  const settle = (s: number) => (s > count ? 1 : s < 1 ? count : s);

  useEffect(() => {
    if (!playing || held || !loop) return;
    const timer = window.setInterval(() => setSlot((s) => settle(s) + 1), AUTOPLAY_MS);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- settle only reads count
  }, [playing, held, loop, count]);

  // Flush the jump with transitions off, then turn them back on before paint.
  useLayoutEffect(() => {
    if (!instant) return;
    trackRef.current?.getBoundingClientRect();
    setInstant(false);
  }, [instant]);

  if (!current) return null;
  const goTo = (nextSlot: number) => {
    setSlot(nextSlot);
    setPlaying(false);
  };
  const slides = featured.map((item, source) => ({ item, source, key: item.agent.agent_instance_id }));
  if (loop) {
    slides.unshift({ item: featured[count - 1], source: count - 1, key: "edge-last" });
    slides.push({ item: featured[0], source: 0, key: "edge-first" });
  }

  return (
    <section
      className={styles.section}
      data-featured-carousel
      aria-roledescription="carousel"
      aria-labelledby="featured-title"
    >
      <div className={styles.head}>
        <h2 id="featured-title" className={styles.title}>
          <SectionMarker />
          {t("rework.home.advanced.featuredTitle")}
        </h2>
        {count > 1 && (
          <div className={styles.controls}>
            <span className={styles.position} aria-hidden="true">
              {position + 1} / {count}
            </span>
            <IconButton
              variant="outlined"
              size="small"
              icon={{ category: "outlined", type: playing ? "pause" : "play_arrow" }}
              onClick={() => setPlaying((value) => !value)}
              aria-label={t(playing ? "rework.home.advanced.pause" : "rework.home.advanced.play")}
            />
            <IconButton
              variant="outlined"
              size="small"
              icon={{ category: "outlined", type: "chevron_left" }}
              onClick={() => goTo(settle(trackPos) - 1)}
              aria-label={t("rework.home.advanced.previous")}
            />
            <IconButton
              variant="outlined"
              size="small"
              icon={{ category: "outlined", type: "chevron_right" }}
              onClick={() => goTo(settle(trackPos) + 1)}
              aria-label={t("rework.home.advanced.next")}
            />
          </div>
        )}
      </div>

      <div
        className={styles.viewport}
        // Announced only when the user moves it: auto-rotation must not interrupt.
        aria-live={playing ? "off" : "polite"}
        onMouseEnter={() => setHeld(true)}
        onMouseLeave={() => setHeld(false)}
        onFocus={() => setHeld(true)}
        onBlur={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setHeld(false);
        }}
      >
        {/* Every slide stays mounted so the track can slide; off-screen ones are inert. */}
        <div
          ref={trackRef}
          className={styles.track}
          data-instant={instant}
          style={{ transform: `translateX(-${trackPos * 100}%)` }}
          onTransitionEnd={(event) => {
            if (event.target !== event.currentTarget || settle(trackPos) === trackPos) return;
            setInstant(true);
            setSlot(settle(trackPos));
          }}
        >
          {slides.map(({ item, source, key }, k) => {
            const { agent } = item;
            const team = teamName(agent.team_id);
            const active = k === trackPos;
            return (
              <article
                key={key}
                className={styles.banner}
                data-featured-slide
                aria-roledescription="slide"
                aria-label={t("rework.home.advanced.slideLabel", {
                  position: source + 1,
                  count,
                  name: agent.display_name,
                })}
                aria-hidden={!active || key.startsWith("edge-")}
                inert={!active}
              >
                <div className={styles.main}>
                  <div className={styles.identity}>
                    <span className={styles.icon}>
                      <Icon category="outlined" type={resolveAgentIcon(agent, agentIconName)} />
                    </span>
                    <div className={styles.nameBlock}>
                      <h3 className={styles.name} title={agent.display_name}>
                        {agent.display_name}
                      </h3>
                      <p className={styles.role} title={agent.role}>
                        {agent.role}
                      </p>
                    </div>
                  </div>
                  {(item.badge || team) && (
                    <div className={styles.chips}>
                      {item.badge && <span className={styles.badge}>{item.badge}</span>}
                      {team && <span className={styles.team}>{t("rework.home.advanced.proposedBy", { team })}</span>}
                    </div>
                  )}
                  <p className={styles.description} title={agent.description || undefined}>
                    {agent.description || t("rework.agentCard.noDescription")}
                  </p>
                </div>
                {(item.highlights?.length ?? 0) > 0 && (
                  <div className={styles.highlights}>
                    <h4 className={styles.highlightsTitle}>{t("rework.home.advanced.highlightsTitle")}</h4>
                    <ul>
                      {item.highlights?.map((line) => (
                        <li key={line}>
                          <span className={styles.bullet} aria-hidden="true" />
                          <span>{line}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                <div className={styles.foot}>
                  <div className={styles.launch}>
                    <AgentChatButton
                      to={`/team/${agent.team_id}/managed-chat/${agent.agent_instance_id}`}
                      aria-label={t("rework.home.advanced.chatWith", { name: agent.display_name })}
                    />
                  </div>
                  {count > 1 ? (
                    <div className={styles.dots}>
                      {featured.map((other, j) => (
                        <button
                          key={other.agent.agent_instance_id}
                          type="button"
                          aria-current={j === source}
                          aria-label={t("rework.home.advanced.show", { name: other.agent.display_name })}
                          onClick={() => goTo(j + 1)}
                        >
                          <span />
                        </button>
                      ))}
                    </div>
                  ) : (
                    <span />
                  )}
                  <Link to={`/team/${agent.team_id}/agents`} className={styles.allAgents}>
                    {t("rework.home.advanced.allAgents")}
                    <Icon category="outlined" type="arrow_forward" />
                  </Link>
                </div>
              </article>
            );
          })}
        </div>
      </div>
    </section>
  );
}

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

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import { resolveAgentIcon } from "@shared/utils/agentIcon.ts";
import { useFrontendProperties } from "../../../../../hooks/useFrontendProperties.ts";
import type { FeaturedHomeAgent } from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
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
  const { agentIconName, homeBannerImageFile } = useFrontendProperties();
  const [index, setIndex] = useState(0);
  // Auto-rotation is opt-out by the user (pause button) and off for reduced motion.
  const [playing, setPlaying] = useState(() => !prefersReducedMotion());
  // Hover or keyboard focus inside the banner holds it without changing `playing`.
  const [held, setHeld] = useState(false);
  const count = featured.length;
  // The list can shrink on refetch (an agent was disabled): stay in range.
  const position = Math.min(index, Math.max(count - 1, 0));
  const current = featured[position];

  useEffect(() => {
    if (!playing || held || count < 2) return;
    const timer = window.setInterval(() => setIndex((i) => (i + 1) % count), AUTOPLAY_MS);
    return () => window.clearInterval(timer);
  }, [playing, held, count]);

  if (!current) return null;
  const { agent } = current;
  const team = teamName(agent.team_id);
  const goTo = (next: number) => {
    setIndex((next + count) % count);
    setPlaying(false);
  };

  return (
    <section className={styles.section} aria-roledescription="carousel" aria-labelledby="featured-title">
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
              onClick={() => goTo(position - 1)}
              aria-label={t("rework.home.advanced.previous")}
            />
            <IconButton
              variant="outlined"
              size="small"
              icon={{ category: "outlined", type: "chevron_right" }}
              onClick={() => goTo(position + 1)}
              aria-label={t("rework.home.advanced.next")}
            />
          </div>
        )}
      </div>

      <article
        className={styles.banner}
        aria-roledescription="slide"
        aria-label={t("rework.home.advanced.slideLabel", { position: position + 1, count, name: agent.display_name })}
        // Announced only when the user moves it: auto-rotation must not interrupt.
        aria-live={playing ? "off" : "polite"}
        onMouseEnter={() => setHeld(true)}
        onMouseLeave={() => setHeld(false)}
        onFocus={() => setHeld(true)}
        onBlur={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setHeld(false);
        }}
      >
        {homeBannerImageFile && (
          <img className={styles.decoration} src={`/images/${homeBannerImageFile}`} alt="" aria-hidden="true" />
        )}
        <div className={styles.main}>
          <div className={styles.identity}>
            <span className={styles.icon}>
              <Icon category="outlined" type={resolveAgentIcon(agent, agentIconName)} />
            </span>
            <div>
              <h3 className={styles.name}>{agent.display_name}</h3>
              <div className={styles.chips}>
                {current.badge && <span className={styles.badge}>{current.badge}</span>}
                {team && <span className={styles.team}>{t("rework.home.advanced.proposedBy", { team })}</span>}
              </div>
            </div>
          </div>
          <p className={styles.pitch}>{agent.role}</p>
          {agent.description && <p className={styles.description}>{agent.description}</p>}
          <Link
            to={`/team/${agent.team_id}/managed-chat/${agent.agent_instance_id}`}
            className={styles.launch}
            aria-label={t("rework.home.advanced.chatWith", { name: agent.display_name })}
          >
            <Icon category="outlined" type="chat_bubble" />
            {t("rework.home.advanced.chatWithAgent")}
          </Link>
        </div>
        {(current.highlights?.length ?? 0) > 0 && (
          <div className={styles.highlights}>
            <h4 className={styles.highlightsTitle}>{t("rework.home.advanced.highlightsTitle")}</h4>
            <ul>
              {current.highlights?.map((line) => (
                <li key={line}>
                  <span className={styles.bullet} aria-hidden="true" />
                  <span>{line}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        <div className={styles.foot}>
          <span />
          {count > 1 ? (
            <div className={styles.dots}>
              {featured.map((item, i) => (
                <button
                  key={item.agent.agent_instance_id}
                  type="button"
                  aria-current={i === position}
                  aria-label={t("rework.home.advanced.show", { name: item.agent.display_name })}
                  onClick={() => goTo(i)}
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
    </section>
  );
}

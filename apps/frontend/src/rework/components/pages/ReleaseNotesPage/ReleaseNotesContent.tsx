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

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button.tsx";
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup.tsx";
import type { ButtonGroupItemProps } from "@shared/atoms/ButtonGroup/ButtonGroupItem/ButtonGroupItem.tsx";
import CodenameModal from "@shared/molecules/CodenameModal/CodenameModal";
import { MarkdownRenderer } from "@shared/molecules/MarkdownRenderer/MarkdownRenderer";
import { getProperty } from "../../../../common/config";
import CODENAME from "../../../../releases/swift.json";
import styles from "./ReleaseNotesContent.module.css";

interface ReleaseCard {
  label: string;
  content: string;
}

async function fetchMarkdown(url: string): Promise<string | null> {
  try {
    const resp = await fetch(url, { cache: "no-cache" });
    if (!resp.ok) return null;
    const ct = resp.headers.get("content-type") ?? "";
    const text = await resp.text();
    const looksHtml =
      ct.includes("text/html") || text.toLowerCase().includes("<!doctype") || text.includes("/@vite/client");
    return looksHtml ? null : text;
  } catch {
    return null;
  }
}

/**
 * Release notes content panel — renders markdown from /release.md (base) and
 * /contrib/{brand}/release.md (brand-specific) when available.
 *
 * Why this component exists:
 * - replaces the old MUI-based ReleaseNotes.tsx with a fully rework-compliant
 *   implementation that uses only design tokens, CSS modules, and rework atoms
 * - meant to be embedded inside ReleaseNotesPage which supplies the page frame
 */
export default function ReleaseNotesContent() {
  const { t } = useTranslation();

  const [cards, setCards] = useState<ReleaseCard[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [hasError, setHasError] = useState(false);
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [codenameOpen, setCodenameOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const load = async () => {
      try {
        const toSlug = (v?: string | null) =>
          (v ?? "")
            .trim()
            .toLowerCase()
            .replace(/[^a-z0-9_-]+/g, "-")
            .replace(/^-+|-+$/g, "");

        const releaseBrand = toSlug(getProperty("releaseBrand") as string | undefined) || "fred";
        const base = (import.meta.env?.BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "";

        const [baseDoc, brandDoc] = await Promise.all([
          fetchMarkdown(`${base}/release.md`),
          fetchMarkdown(`${base}/contrib/${releaseBrand}/release.md`),
        ]);

        const loaded: ReleaseCard[] = [];
        if (baseDoc) loaded.push({ label: t("rework.releaseNotes.baseRelease"), content: baseDoc });
        if (brandDoc)
          loaded.push({ label: t("rework.releaseNotes.brandRelease", { brand: releaseBrand }), content: brandDoc });

        if (loaded.length === 0) {
          setHasError(true);
        } else {
          setCards(loaded);
        }
      } catch {
        setHasError(true);
      } finally {
        setIsLoading(false);
      }
    };

    void load();
  }, [t]);

  const tabItems: ButtonGroupItemProps[] = useMemo(
    () => cards.map((card, idx) => ({ label: card.label, onClick: () => setSelectedIdx(idx) })),
    [cards],
  );

  const selectedContent = cards[selectedIdx]?.content ?? "";

  const handleCopy = async () => {
    if (!selectedContent) return;
    try {
      await navigator.clipboard.writeText(selectedContent);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard unavailable — silent fallback
    }
  };

  return (
    <div className={styles.root}>
      <div className={styles.toolbar}>
        {cards.length > 1 && <ButtonGroup items={tabItems} size="small" color="primary" />}
        <div className={styles.actions}>
          <button className={styles.codenameBadge} type="button" onClick={() => setCodenameOpen(true)}>
            {CODENAME.codename} · {CODENAME.version}
          </button>
          {!isLoading && !hasError && (
            <Button color="on-surface" variant="text" size="small" type="button" onClick={handleCopy}>
              {copied ? t("rework.releaseNotes.copied") : t("rework.releaseNotes.copy")}
            </Button>
          )}
        </div>
      </div>

      <div className={styles.scrollArea}>
        {!isLoading && !hasError && <MarkdownRenderer text={selectedContent} />}
        {!isLoading && hasError && <p className={styles.empty}>{t("rework.releaseNotes.empty")}</p>}
      </div>

      <CodenameModal open={codenameOpen} onClose={() => setCodenameOpen(false)} data={CODENAME} />
    </div>
  );
}

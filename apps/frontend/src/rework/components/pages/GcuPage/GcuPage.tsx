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

import Button from "@shared/atoms/Button/Button.tsx";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { platformPath } from "../../../../common/platformAccess";
import { useFrontendProperties } from "../../../../hooks/useFrontendProperties.ts";
import {
  useAcceptTermsMutation,
  useOnboardingStatusQuery,
} from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { MarkdownRenderer } from "@shared/molecules/MarkdownRenderer/MarkdownRenderer";
import { useLegalMarkdownState } from "@hooks/useLegalMarkdown.ts";
import styles from "./GcuPage.module.css";

export default function GcuPage({ version }: { version: string }) {
  const { t } = useTranslation();
  const [accept, result] = useAcceptTermsMutation();
  const state = useOnboardingStatusQuery();
  const [failed, setFailed] = useState(false);
  return (
    <>
      {failed && (
        <div role="alert">
          <p>{t("rework.manager.unavailable")}</p>
          <Button color="primary" variant="outlined" size="medium" onClick={() => window.location.reload()}>
            {t("rework.bootstrap.reload")}
          </Button>
        </div>
      )}
      <GcuPageContent
        version={version}
        isLoading={result.isLoading || state.isFetching}
        onAccept={async () => {
          setFailed(false);
          try {
            await accept({ termsRequest: { version } }).unwrap();
            await state.refetch().unwrap();
          } catch {
            setFailed(true);
          }
        }}
      />
    </>
  );
}

export function GcuPageContent({
  accepted = false,
  isLoading,
  onAccept,
  version,
}: {
  version?: string | null;
} & (
  | { accepted: true; isLoading?: never; onAccept?: never }
  | { accepted?: false; isLoading: boolean; onAccept: () => Promise<void> }
)) {
  const { t } = useTranslation();
  const { gcuVersion } = useFrontendProperties();
  const { markdown: gcuMarkdown, failed } = useLegalMarkdownState("gcu");
  const [hasReachedBottom, setHasReachedBottom] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    setHasReachedBottom(false);
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setHasReachedBottom(true);
          observer.unobserve(entry.target);
        } else {
          setHasReachedBottom(false);
        }
      },
      // Any overlap counts: Firefox's fractional positions keep a full-visibility
      // threshold from ever tripping on a 1px sentinel.
      { threshold: 0 },
    );

    if (bottomRef.current) {
      observer.observe(bottomRef.current);
    }

    return () => observer.disconnect();
  }, [gcuMarkdown]);

  return (
    <div className={styles.gcuContainer}>
      <div className={styles.gcuTitle}>{t("rework.gcu.title")}</div>
      {failed && (
        <div role="alert">
          <p>{t("rework.gcu.unavailable")}</p>
          <Button color="primary" variant="outlined" size="medium" onClick={() => window.location.reload()}>
            {t("rework.bootstrap.reload")}
          </Button>
        </div>
      )}
      <div className={styles.gcuContent}>
        <MarkdownRenderer text={gcuMarkdown} />
        <div ref={bottomRef} className={styles.gcuEnd} />
      </div>
      <div className={styles.gcuActions}>
        {accepted ? (
          <Button
            color={"primary"}
            variant={"filled"}
            size={"medium"}
            onClick={() => window.location.replace(platformPath("/"))}
          >
            {t("rework.gcu.backToApp")}
          </Button>
        ) : (
          <>
            <span className={styles.gcuLockInformation}>{t("rework.gcu.lockInformation")}</span>
            <Button
              color={"primary"}
              variant={"filled"}
              size={"medium"}
              disabled={
                !(version === undefined ? gcuVersion : version) || !gcuMarkdown || !hasReachedBottom || isLoading
              }
              onClick={onAccept}
            >
              {t("rework.gcu.validate")}
            </Button>
          </>
        )}
      </div>
    </div>
  );
}

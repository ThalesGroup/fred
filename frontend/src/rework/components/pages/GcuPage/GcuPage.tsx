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
import { Link } from "react-router-dom";
import { useFrontendProperties } from "../../../../hooks/useFrontendProperties.ts";
import {
  useGetUserDetailsControlPlaneV1UserGetQuery,
  useValidateGcuControlPlaneV1GcuPostMutation,
} from "../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import styles from "./GcuPage.module.css";

export default function GcuPage() {
  const { t } = useTranslation();
  const [trigger, { isLoading }] = useValidateGcuControlPlaneV1GcuPostMutation();
  const { data: userDetails, refetch } = useGetUserDetailsControlPlaneV1UserGetQuery();
  const { gcuVersion } = useFrontendProperties();

  const [hasReachedBottom, setHasReachedBottom] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setHasReachedBottom(true);
          observer.unobserve(entry.target);
        } else {
          setHasReachedBottom(false);
        }
      },
      {
        root: null,
        threshold: 1.0,
      },
    );

    if (bottomRef.current) {
      observer.observe(bottomRef.current);
    }

    return () => observer.disconnect();
  }, []);

  const handleAcceptGcu = async () => {
    await trigger().unwrap();
    refetch();
  };

  return (
    <div className={styles.gcuContainer}>
      <div className={styles.gcuTitle}>{t("rework.gcu.title")}</div>
      <div className={styles.gcuContent}></div>
      <div className={styles.gcuActions}>
        {gcuVersion && userDetails?.cguValidated != null && userDetails.cguValidated.toString() === gcuVersion ? (
          <Link to={"/"}>
            <Button color={"primary"} variant={"filled"} size={"medium"}>
              {t("rework.gcu.backToApp")}
            </Button>
          </Link>
        ) : (
          <>
            <span className={styles.gcuLockInformation}>{t("rework.gcu.lockInformation")}</span>
            <Button
              color={"primary"}
              variant={"filled"}
              size={"medium"}
              disabled={!hasReachedBottom || isLoading}
              onClick={handleAcceptGcu}
            >
              {t("rework.gcu.validate")}
            </Button>
          </>
        )}
      </div>
    </div>
  );
}

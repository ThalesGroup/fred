import styles from "./GcuPage.module.css";
import Button from "@shared/atoms/Button/Button.tsx";
import { useTranslation } from "react-i18next";
import { useEffect, useRef, useState } from "react";
import {
  useGetUserDetailsControlPlaneV1UserGetQuery,
  useValidateGcuControlPlaneV1GcuPostMutation,
} from "../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import { useFrontendProperties } from "../../../../hooks/useFrontendProperties.ts";
import { Link } from "react-router-dom";

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
      <div className={styles.gcuContent}>
      </div>
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

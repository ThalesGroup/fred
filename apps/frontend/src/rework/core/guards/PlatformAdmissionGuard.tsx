// SPDX-License-Identifier: Apache-2.0
import { PropsWithChildren, useEffect } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import GcuPage from "@components/pages/GcuPage/GcuPage";
import { usePlatformAccessStatusQuery } from "../../../slices/controlPlane/controlPlaneApiEnhancements";
import { handlePlatformAccessDenial } from "../../../common/platformAccess";

export default function PlatformAdmissionGuard({ children }: PropsWithChildren) {
  const { t } = useTranslation();
  const result = usePlatformAccessStatusQuery(undefined, { refetchOnMountOrArgChange: true });
  useEffect(() => {
    if (result.data && !result.data.admitted) handlePlatformAccessDenial(403, { detail: "platform_access_denied" });
  }, [result.data]);
  if (result.isError)
    return (
      <main>
        <p role="alert">{t("rework.platformAccess.failed")}</p>
        <Button color="primary" variant="filled" size="medium" onClick={() => void result.refetch()}>
          {t("rework.platformAccess.retry")}
        </Button>
      </main>
    );
  if (!result.data || !result.data.admitted) return <p>{t("rework.platformAccess.loading")}</p>;
  if (result.data.cgu_required) return <GcuPage />;
  return <>{children}</>;
}

// SPDX-License-Identifier: Apache-2.0
import { useTranslation } from "react-i18next";
import { platformPath } from "../../../../common/platformAccess";
import PlatformAccessError from "./PlatformAccessError";

export default function PlatformAccessDeniedPage() {
  const { t } = useTranslation();
  return (
    <PlatformAccessError
      title={t("rework.platformAccess.deniedTitle")}
      message={t("rework.platformAccess.deniedMessage")}
      retry={() => window.location.replace(platformPath("/"))}
    />
  );
}

// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { type PropsWithChildren } from "react";
import { useTranslation } from "react-i18next";
import GcuPage from "@components/pages/GcuPage/GcuPage";
import MainLayout from "@shared/layouts/MainLayout/MainLayout";
import Button from "@shared/atoms/Button/Button";
import { useOnboardingStatusQuery } from "../../../slices/fredManager/fredManagerApiEnhancements";
import { useRefetchOnWindowFocus } from "../hooks/crossSessionRefresh";

export default function GcuGuard({ children }: PropsWithChildren) {
  const { t } = useTranslation();
  const state = useOnboardingStatusQuery(undefined, { refetchOnMountOrArgChange: true });
  useRefetchOnWindowFocus(state.refetch, false);
  let content;
  if (state.isLoading) content = <p role="status">{t("common.loading")}</p>;
  else if (state.isError || !state.data)
    content = (
      <div role="alert">
        <p>{t("rework.manager.unavailable")}</p>
        <Button color="primary" variant="outlined" size="medium" onClick={() => void state.refetch()}>
          {t("rework.provisioning.retryAuthority")}
        </Button>
      </div>
    );
  else if (state.data.gcu_version && state.data.acceptance?.version !== state.data.gcu_version)
    content = <GcuPage key={state.data.gcu_version} version={state.data.gcu_version} />;
  else return <>{children}</>;
  return <MainLayout navigation={false}>{content}</MainLayout>;
}

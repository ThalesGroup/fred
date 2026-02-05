import AssistantIcon from "@mui/icons-material/Assistant";
import { Box, CssBaseline } from "@mui/material";
import { useTranslation } from "react-i18next";
import { EmptyState } from "../components/EmptyState";
import { useGetFrontendConfigAgenticV1ConfigFrontendSettingsGetQuery } from "../slices/agentic/agenticOpenApi";

export function ComingSoon() {
  const { t } = useTranslation();

  const { data: frontendConfig } = useGetFrontendConfigAgenticV1ConfigFrontendSettingsGetQuery();
  const { siteDisplayName } = frontendConfig.frontend_settings.properties || {};

  // todo: use `useFrontendProperties` and `DynamicSvgIcon` after merge with team branch
  //   const { agentIconName } = useFrontendProperties();
  //   const icon = agentIconName ? (
  //     <DynamicSvgIcon iconPath={`images/${agentIconName}.svg`} color="action" />
  //   ) : (
  //     <AssistantIcon />
  //   );

  return (
    <>
      <CssBaseline enableColorScheme />
      <Box
        sx={{
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          height: "100vh",
          width: "100vw",
        }}
      >
        <EmptyState
          icon={<AssistantIcon />}
          title={t("comingSoon.title", { siteDisplayName })}
          description={t("comingSoon.description")}
          descriptionMaxWidth={"60ch"}
        />
      </Box>
    </>
  );
}

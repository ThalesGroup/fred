import AssistantIcon from "@mui/icons-material/Assistant";
import { Box, CssBaseline } from "@mui/material";
import { useTranslation } from "react-i18next";
import { DynamicSvgIcon } from "../components/DynamicSvgIcon";
import { EmptyState } from "../components/EmptyState";
import { useFrontendProperties } from "../hooks/useFrontendProperties";

export function ComingSoon() {
  const { t } = useTranslation();

  const { siteDisplayName, agentIconName } = useFrontendProperties();
  const icon = agentIconName ? (
    <DynamicSvgIcon iconPath={`images/${agentIconName}.svg`} color="action" />
  ) : (
    <AssistantIcon />
  );

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
          icon={icon}
          title={t("comingSoon.title", { siteDisplayName })}
          description={t("comingSoon.description")}
          descriptionMaxWidth={"60ch"}
        />
      </Box>
    </>
  );
}

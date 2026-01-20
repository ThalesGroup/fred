import AddIcon from "@mui/icons-material/Add";
import { Button } from "@mui/material";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

export function SideBarNewConversationButton() {
  const { t } = useTranslation();

  return (
    <Button component={Link} to="/" variant="outlined" size="small" startIcon={<AddIcon />}>
      {t("common.create")}
    </Button>
  );
}

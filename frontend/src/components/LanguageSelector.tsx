// components/common/LanguageSelector.tsx
import { useTranslation } from "react-i18next";
import { IconButton, Tooltip, Box } from "@mui/material";

export const LanguageSelector = () => {
  const { i18n } = useTranslation();
  const currentLang = i18n.language;

  const changeLanguage = (lang: string) => {
    i18n.changeLanguage(lang);
  };

  return (
    <Box sx={{ display: "flex", gap: 1 }}>
      <Tooltip title="Français" arrow>
        <IconButton
          onClick={() => changeLanguage("fr")}
          size="small"
          sx={{
            fontSize: "0.75rem",
            //fontWeight: "bold",
            opacity: currentLang === "fr" ? 1 : 0.4,
            borderRadius: 1,
            border: currentLang === "fr" ? "1px solid" : "none",
            borderColor: "primary.main",
            color: "text.primary",
            px: 1,
          }}
        >
          FR
        </IconButton>
      </Tooltip>
      <Tooltip title="English" arrow>
        <IconButton
          onClick={() => changeLanguage("en")}
          size="small"
          sx={{
            fontSize: "0.75rem",
            //fontWeight: "bold",
            opacity: currentLang === "en" ? 1 : 0.4,
            borderRadius: 1,
            border: currentLang === "en" ? "1px solid" : "none",
            borderColor: "primary.main",
            color: "text.primary",
            px: 1,
          }}
        >
          EN
        </IconButton>
      </Tooltip>
    </Box>
  );
};

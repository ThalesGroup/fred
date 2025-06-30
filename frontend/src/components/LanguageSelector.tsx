import { useTranslation } from "react-i18next";
import { IconButton, Tooltip, Box } from "@mui/material";

export const LanguageSelector = () => {
  const { i18n } = useTranslation();
  const currentLang = i18n.language;

  const changeLanguage = (lang: string) => {
    i18n.changeLanguage(lang);
  };

  return (
    <Box sx={{ display: "flex", alignItems: "center", mt: 1 }}>
      <Tooltip title="Français" placement="top">
        <IconButton
          onClick={() => changeLanguage("fr")}
          size="small"
          sx={{
            opacity: currentLang === "fr" ? 1 : 0.5,
            "&:hover": { opacity: 1 },
          }}
        >
          FR
        </IconButton>
      </Tooltip>

      <Tooltip title="English" placement="top">
        <IconButton
          onClick={() => changeLanguage("en")}
          size="small"
          sx={{
            opacity: currentLang === "en" ? 1 : 0.5,
            "&:hover": { opacity: 1 },
          }}
        >
          EN
        </IconButton>
      </Tooltip>
    </Box>
  );
};

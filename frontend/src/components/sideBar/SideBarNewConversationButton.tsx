import AddIcon from "@mui/icons-material/Add";
import { Button, ButtonProps } from "@mui/material";
import { styled } from "@mui/material/styles";
import { useTranslation } from "react-i18next";
import { Link, LinkProps } from "react-router-dom";

const GradientButton = styled(Button)<ButtonProps<typeof Link, LinkProps>>(({ theme }) => ({
  display: "inline-flex",
  alignItems: "center",
  gap: "8px",
  padding: "8px 20px",
  background: "transparent",
  border: "none",
  borderRadius: "50px",
  fontSize: "14px",
  fontWeight: 500,
  color: theme.palette.text.primary,
  position: "relative",
  textTransform: "none",
  minWidth: "auto",
  isolation: "isolate",
  "&::before": {
    content: '""',
    position: "absolute",
    inset: "-3px",
    borderRadius: "50px",
    padding: "3px",
    background:
      "radial-gradient(circle at 0% 50%, rgba(255, 160, 130, 0.9) 0%, transparent 60%), radial-gradient(circle at 50% 100%, rgba(190, 130, 255, 0.9) 0%, transparent 60%), radial-gradient(circle at 100% 50%, rgba(80, 140, 255, 0.9) 0%, transparent 60%), radial-gradient(circle at 50% 0%, rgba(100, 255, 235, 0.9) 0%, transparent 60%), #ffffff",
    WebkitMask: "linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0)",
    WebkitMaskComposite: "xor",
    maskComposite: "exclude",
    zIndex: -1,
    transition: "background 0.2s ease",
  },
  "&::after": {
    content: '""',
    position: "absolute",
    inset: 0,
    background: theme.palette.background.default,
    borderRadius: "50px",
    zIndex: -1,
  },
  "& .MuiButton-label, & > *": {
    position: "relative",
    zIndex: 1,
  },
  "&:hover::after": {
    background: theme.palette.action.hover,
    mixBlendMode: "overlay",
  },
  "&:active": {
    transform: "translateY(0)",
  },
  "& .MuiButton-startIcon": {
    fontSize: "18px",
    fontWeight: 300,
    margin: 0,
  },
}));

export function SideBarNewConversationButton() {
  const { t } = useTranslation();

  return (
    <GradientButton component={Link} to="/new-chat" startIcon={<AddIcon />} sx={{ width: "100%" }}>
      {t("sidebar.newChat")}
    </GradientButton>
  );
}

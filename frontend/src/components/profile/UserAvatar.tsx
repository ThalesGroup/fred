import { Avatar, useTheme } from "@mui/material";
import { KeyCloakService } from "../../security/KeycloakService";

export function UserAvatar() {
  const theme = useTheme();

  const fullName = KeyCloakService.GetUserFullName();
  const userRoles = KeyCloakService.GetUserRoles();

  const getInitials = () => {
    if (!fullName) return "U";
    const parts = fullName.trim().split(/\s+/);
    if (parts.length > 1) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
    return fullName.substring(0, 2).toUpperCase();
  };

  const getAvatarColor = () => {
    if (userRoles.includes("admin")) return theme.palette.error.main;
    if (userRoles.includes("manager")) return theme.palette.secondary.dark;
    return theme.palette.primary.main;
  };

  return (
    <Avatar
      sx={{
        backgroundColor: getAvatarColor(),
      }}
    >
      {getInitials()}
    </Avatar>
  );
}

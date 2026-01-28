import { Avatar, useTheme } from "@mui/material";
import { KeyCloakService } from "../../security/KeycloakService";
import { getInitials } from "../../utils/getInitials";

export function UserAvatar() {
  const theme = useTheme();

  const fullName = KeyCloakService.GetUserFullName();
  const userRoles = KeyCloakService.GetUserRoles();

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
      {getInitials(fullName)}
    </Avatar>
  );
}

// components/profile/ProfileCard.tsx
import {
  Avatar,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  Grid2,
  Stack,
  Typography,
  useTheme,
} from "@mui/material";
import AccountCircleIcon from "@mui/icons-material/AccountCircle";
import AdminPanelSettingsIcon from "@mui/icons-material/AdminPanelSettings";
import SecurityIcon from "@mui/icons-material/Security";
import CodeIcon from "@mui/icons-material/Code";
import LogoutIcon from "@mui/icons-material/Logout";
import EmailIcon from "@mui/icons-material/Email";
import AccessTimeIcon from "@mui/icons-material/AccessTime";
import FingerprintIcon from "@mui/icons-material/Fingerprint";

interface ProfileCardProps {
  username: string;
  userRoles: string[];
  tokenParsed: any;
  fullName: string;
  userEmail: string;
  userId: string;
  formatAuthDate: () => string;
  formatExpDate: () => string;
  onLogout: () => void;
}

export function ProfileCard({
  username,
  userRoles,
  fullName,
  userEmail,
  userId,
  formatAuthDate,
  formatExpDate,
  onLogout,
}: ProfileCardProps) {
  const theme = useTheme();

  const getInitials = () => {
    if (!username) return "U";
    const names = username.split(" ");
    if (names.length > 1) return `${names[0][0]}${names[1][0]}`.toUpperCase();
    return username.substring(0, 2).toUpperCase();
  };

  const getAvatarColor = () => {
    if (userRoles.includes("admin")) return theme.palette.error.main;
    if (userRoles.includes("manager")) return theme.palette.secondary.dark;
    return theme.palette.primary.main;
  };

  const getRoleIcon = (role: string) => {
    if (role.includes("admin")) return <AdminPanelSettingsIcon fontSize="small" />;
    if (role.includes("user")) return <AccountCircleIcon fontSize="small" />;
    if (role.includes("manager")) return <SecurityIcon fontSize="small" />;
    return <CodeIcon fontSize="small" />;
  };

  return (
    <Grid2 size={{ xs: 12 }}>
      <Card
        elevation={3}
        sx={{
          borderRadius: 2,
          overflow: "visible",
          position: "relative",
          pt: 7,
        }}
      >
        <Box
          sx={{
            position: "absolute",
            top: -40,
            left: "50%",
            transform: "translateX(-50%)",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
          }}
        >
          <Avatar
            sx={{
              width: 80,
              height: 80,
              fontSize: "1.8rem",
              fontWeight: "bold",
              backgroundColor: getAvatarColor(),
            }}
          >
            {getInitials()}
          </Avatar>
        </Box>

        <CardContent sx={{ pt: 3, pb: 4 }}>
          <Typography variant="h5" fontWeight="bold" sx={{ mb: 1, textAlign: "center" }}>
            {fullName}
          </Typography>
          <Typography variant="body1" color="text.secondary" sx={{ mb: 3, textAlign: "center" }}>
            @{username}
          </Typography>

          <Divider sx={{ mb: 3 }} />

          <Grid2 container spacing={2} sx={{ mb: 3, alignItems: "center" }}>
            <Grid2 size={{ xs: 12, sm: 6 }}>
              <Box display="flex" alignItems="center" justifyContent="center" mb={1}>
                <EmailIcon sx={{ mr: 2, color: "primary.main" }} />
                <Typography variant="body2" fontWeight="medium">Email</Typography>
              </Box>
              <Typography variant="body1" textAlign="center">{userEmail}</Typography>
            </Grid2>

            <Grid2 size={{ xs: 12, sm: 6 }}>
              <Box display="flex" alignItems="center" justifyContent="center" mb={1}>
                <FingerprintIcon sx={{ mr: 2, color: "primary.main" }} />
                <Typography variant="body2" fontWeight="medium">User ID</Typography>
              </Box>
              <Typography variant="body1" textAlign="center" sx={{ wordBreak: "break-all" }}>{userId}</Typography>
            </Grid2>

            <Grid2 size={{ xs: 12, sm: 6 }}>
              <Box display="flex" alignItems="center" justifyContent="center" mb={1}>
                <AccessTimeIcon sx={{ mr: 2, color: "primary.main" }} />
                <Typography variant="body2" fontWeight="medium">Last Authentication</Typography>
              </Box>
              <Typography variant="body1" textAlign="center">{formatAuthDate()}</Typography>
            </Grid2>

            <Grid2 size={{ xs: 12, sm: 6 }}>
              <Box display="flex" alignItems="center" justifyContent="center" mb={1}>
                <AccessTimeIcon sx={{ mr: 2, color: "primary.main" }} />
                <Typography variant="body2" fontWeight="medium">Session Expiration</Typography>
              </Box>
              <Typography variant="body1" textAlign="center">{formatExpDate()}</Typography>
            </Grid2>
          </Grid2>

          <Divider sx={{ mb: 3 }} />

          <Typography
            variant="h6"
            sx={{ mb: 2, display: "flex", alignItems: "center", justifyContent: "center" }}
          >
            <SecurityIcon sx={{ mr: 1 }} /> User Roles
          </Typography>

          <Box display="flex" flexWrap="wrap" justifyContent="center" gap={1} mb={3}>
            {userRoles.map((role) => (
              <Chip
                key={role}
                icon={getRoleIcon(role)}
                label={role}
                sx={{
                  fontWeight: "medium",
                  py: 2,
                  backgroundColor: theme.palette.mode === "dark" ? "primary.dark" : "primary.light",
                  color: theme.palette.mode === "dark" ? "white" : "primary.dark",
                  transition: "all 0.2s ease",
                  "&:hover": {
                    backgroundColor: theme.palette.primary.main,
                    color: "white",
                    transform: "translateY(-2px)",
                  },
                }}
              />
            ))}
          </Box>

          <Stack direction={{ xs: "column", sm: "row" }} spacing={2} justifyContent="center">
            <Button
              variant="contained"
              color="primary"
              startIcon={<LogoutIcon />}
              onClick={onLogout}
              sx={{ borderRadius: 2, px: 3, boxShadow: 2 }}
            >
              Logout
            </Button>
          </Stack>
        </CardContent>
      </Card>
    </Grid2>
  );
}

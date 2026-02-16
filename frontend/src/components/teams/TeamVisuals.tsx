import GroupsIcon from "@mui/icons-material/Groups";
import { alpha, Avatar, AvatarProps, Box, SxProps, Theme, Typography } from "@mui/material";
import { useEffect, useMemo, useState } from "react";
import { getInitials } from "../../utils/getInitials";

const fallbackColors = (theme: Theme) => {
  if (theme.palette.mode === "dark") {
    return {
      bg: alpha(theme.palette.primary.light, 0.24),
      fg: theme.palette.primary.light,
      border: alpha(theme.palette.primary.light, 0.42),
    };
  }
  return {
    bg: alpha(theme.palette.primary.main, 0.14),
    fg: theme.palette.primary.dark,
    border: alpha(theme.palette.primary.main, 0.28),
  };
};

const normalizeImageUrl = (imageUrl?: string | null): string => (imageUrl || "").trim();

const reservedRoleTeamNames = new Set(["editor", "editors", "viewer", "viewers"]);

const isReservedRoleTeam = (teamName?: string | null): boolean => {
  const normalizedName = (teamName || "").trim().toLowerCase();
  return reservedRoleTeamNames.has(normalizedName);
};

const teamInitials = (teamName?: string | null): string => {
  if (isReservedRoleTeam(teamName)) return "";
  return getInitials(teamName || "Team");
};

type TeamAvatarProps = Omit<AvatarProps, "src" | "children"> & {
  teamName?: string | null;
  imageUrl?: string | null;
};

export function TeamAvatar({ teamName, imageUrl, sx, imgProps, ...avatarProps }: TeamAvatarProps) {
  const normalizedImageUrl = normalizeImageUrl(imageUrl);
  const [failedToLoad, setFailedToLoad] = useState(false);
  const reservedRoleTeam = isReservedRoleTeam(teamName);

  useEffect(() => {
    setFailedToLoad(false);
  }, [normalizedImageUrl]);

  const hasImage = normalizedImageUrl.length > 0 && !failedToLoad;
  const mergedSx = useMemo<SxProps<Theme>>(
    () => [
      (theme: Theme) => {
        const colors = fallbackColors(theme);
        return {
          backgroundColor: colors.bg,
          color: colors.fg,
          border: `1px solid ${colors.border}`,
          fontWeight: 700,
        };
      },
      ...(Array.isArray(sx) ? sx : sx ? [sx] : []),
    ],
    [sx],
  );

  return (
    <Avatar
      {...avatarProps}
      src={hasImage ? normalizedImageUrl : undefined}
      imgProps={{
        ...imgProps,
        onError: (event) => {
          setFailedToLoad(true);
          imgProps?.onError?.(event);
        },
      }}
      sx={mergedSx}
    >
      {reservedRoleTeam ? <GroupsIcon fontSize="small" /> : teamInitials(teamName)}
    </Avatar>
  );
}

type TeamBannerProps = {
  teamName?: string | null;
  imageUrl?: string | null;
  alt?: string;
  height?: string | number;
  width?: string | number;
  borderRadius?: string | number;
  sx?: SxProps<Theme>;
};

export function TeamBanner({
  teamName,
  imageUrl,
  alt,
  height = "6rem",
  width = "100%",
  borderRadius = 0,
  sx,
}: TeamBannerProps) {
  const normalizedImageUrl = normalizeImageUrl(imageUrl);
  const [failedToLoad, setFailedToLoad] = useState(false);
  const reservedRoleTeam = isReservedRoleTeam(teamName);

  useEffect(() => {
    setFailedToLoad(false);
  }, [normalizedImageUrl]);

  const hasImage = normalizedImageUrl.length > 0 && !failedToLoad;

  if (hasImage) {
    return (
      <Box
        component="img"
        src={normalizedImageUrl}
        alt={alt || `${teamName || "Team"} banner`}
        onError={() => setFailedToLoad(true)}
        sx={[
          {
            width,
            height,
            borderRadius,
            objectFit: "cover",
            backgroundRepeat: "no-repeat",
            display: "block",
          },
          ...(Array.isArray(sx) ? sx : sx ? [sx] : []),
        ]}
      />
    );
  }

  return (
    <Box
      sx={[
        (theme: Theme) => {
          const colors = fallbackColors(theme);
          return {
            width,
            height,
            borderRadius,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            backgroundColor: colors.bg,
            color: colors.fg,
            border: `1px solid ${colors.border}`,
            userSelect: "none",
          };
        },
        ...(Array.isArray(sx) ? sx : sx ? [sx] : []),
      ]}
    >
      {reservedRoleTeam ? (
        <GroupsIcon sx={{ fontSize: "1.4rem" }} />
      ) : (
        <Typography sx={{ fontSize: "1.1rem", fontWeight: 700, letterSpacing: "0.02em" }}>
          {teamInitials(teamName)}
        </Typography>
      )}
    </Box>
  );
}

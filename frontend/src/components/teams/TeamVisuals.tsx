import { alpha, Avatar, AvatarProps, Box, SxProps, Theme, Typography } from "@mui/material";
import { useEffect, useMemo, useState } from "react";
import { getInitials } from "../../utils/getInitials";

const fallbackColors = (theme: Theme) => {
  return {
    bg: alpha(theme.palette.primary.main, 0.16),
    fg: theme.palette.getContrastText(alpha(theme.palette.primary.main, 0.16)),
  };
};

const normalizeImageUrl = (imageUrl?: string | null): string => (imageUrl || "").trim();

type TeamAvatarProps = Omit<AvatarProps, "src" | "children"> & {
  teamName?: string | null;
  imageUrl?: string | null;
};

export function TeamAvatar({ teamName, imageUrl, sx, slotProps, ...avatarProps }: TeamAvatarProps) {
  const normalizedImageUrl = normalizeImageUrl(imageUrl);
  const [failedToLoad, setFailedToLoad] = useState(false);

  useEffect(() => {
    setFailedToLoad(false);
  }, [normalizedImageUrl]);

  const hasImage = normalizedImageUrl.length > 0 && !failedToLoad;
  const mergedSx = useMemo<SxProps<Theme>>(
    () => [
      (theme: Theme) => {
        const colors = fallbackColors(theme);
        return {
          "&.MuiAvatar-colorDefault": {
            backgroundColor: colors.bg,
            color: colors.fg,
          },
        };
      },
      ...(Array.isArray(sx) ? sx : sx ? [sx] : []),
    ],
    [sx, failedToLoad],
  );

  return (
    <Avatar
      {...avatarProps}
      src={hasImage ? normalizedImageUrl : undefined}
      slotProps={{
        ...slotProps,
        img: {
          ...(typeof slotProps?.img === "function" ? {} : slotProps?.img),
          onError: (event) => {
            setFailedToLoad(true);
            if (typeof slotProps?.img !== "function") {
              slotProps?.img?.onError?.(event);
            }
          },
        },
      }}
      sx={mergedSx}
    >
      {getInitials(teamName)}
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
            userSelect: "none",
          };
        },
        ...(Array.isArray(sx) ? sx : sx ? [sx] : []),
      ]}
    >
      <Typography sx={{ fontSize: "1.1rem", letterSpacing: "0.02em" }}>{getInitials(teamName)}</Typography>
    </Box>
  );
}

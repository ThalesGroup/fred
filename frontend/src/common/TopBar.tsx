import { Box, Container, Fade, Grid2, Typography, Chip, useTheme } from "@mui/material";
import { ReactNode } from "react";

interface TopBarProps {
  title: string;
  description: string;
  backgroundUrl: string;
  children?: ReactNode; // e.g. right-hand content like date picker
  fadeIn?: boolean;
  leftLg?: number;
}

export const TopBar = ({
  title,
  description,
  backgroundUrl,
  children,
  fadeIn = true,
  leftLg = 8,
}: TopBarProps) => {
  const theme = useTheme();
  const isDarkTheme = theme.palette.mode === "dark";
  const leftGrid = leftLg ?? 8;
  const rightGrid = 12 - leftGrid;
  
  const heroBackground = isDarkTheme
    ? `linear-gradient(${theme.palette.heroBackgroundGrad.gradientFrom}, ${theme.palette.heroBackgroundGrad.gradientTo}), url('${backgroundUrl}')`
    : `linear-gradient(${theme.palette.heroBackgroundGrad.gradientFrom}, ${theme.palette.heroBackgroundGrad.gradientTo}), url('${backgroundUrl}')`;

  return (
    <Box
      sx={{
        position: "relative",
        backgroundImage: heroBackground,
        backgroundSize: "cover",
        backgroundPosition: "center",
        mb: 3,
        borderRadius: 2,
        boxShadow: theme.shadows[4],
      }}
    >
      <Container maxWidth="xl">
        <Fade in={fadeIn} timeout={1000}>
          <Box sx={{ py: 3 }}>
            <Grid2 container spacing={3} alignItems="center">
              <Grid2 size={{ xs: 12, md: 7, lg: leftGrid }}>
                <Box>
                  <Chip
                    label={title}
                    color="primary"
                  />
                  <Typography
                    variant="body1"
                    color="textSecondary"
                    sx={{ maxWidth: "300px", mt: 1 }}
                  >
                    {description}
                  </Typography>
                </Box>
              </Grid2>
              <Grid2 size={{ xs: 12, md: 5, lg: rightGrid }}>
                {children}
              </Grid2>
            </Grid2>
          </Box>
        </Fade>
      </Container>
    </Box>
  );
};
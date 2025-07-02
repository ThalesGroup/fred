import { Box, Card, CardContent, Grid2, Typography, useTheme } from "@mui/material";
import CodeIcon from "@mui/icons-material/Code";
import { useTranslation } from "react-i18next";

interface ProfileTokenProps {
  tokenParsed: any;
}

export function ProfileToken({ tokenParsed }: ProfileTokenProps) {
  const theme = useTheme();
  const { t } = useTranslation();

  return (
    <Grid2 size={{ xs: 12 }}>
      <Card elevation={3} sx={{ borderRadius: 2 }}>
        <CardContent>
          <Typography
            variant="h6"
            sx={{
              mb: 2,
              fontWeight: "medium",
              display: "flex",
              alignItems: "center",
            }}
          >
            <CodeIcon sx={{ mr: 1 }} /> {t("profile.token.title")}
          </Typography>
          <Box
            sx={{
              backgroundColor: theme.palette.mode === "dark" ? "grey.800" : "grey.100",
              borderRadius: 1,
              p: 2,
              maxHeight: "400px",
              overflowY: "auto",
              overflowX: "auto",
              border: `1px solid ${theme.palette.divider}`,
              "&::-webkit-scrollbar": {
                width: "8px",
                height: "8px",
              },
              "&::-webkit-scrollbar-thumb": {
                borderRadius: "4px",
              },
            }}
          >
            <pre
              style={{
                margin: 0,
                fontFamily: '"Roboto Mono", monospace',
                fontSize: "0.75rem",
              }}
            >
              {tokenParsed ? JSON.stringify(tokenParsed, null, 2) : t("profile.token.none")}
            </pre>
          </Box>
        </CardContent>
      </Card>
    </Grid2>
  );
}

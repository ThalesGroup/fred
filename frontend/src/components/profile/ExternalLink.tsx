import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import { Box, IconButton, Typography } from "@mui/material";
import { Link } from "react-router-dom";

export function ExternalLink({ href, label }: { href: string; label: string }) {
  return (
    <Link to={href} target="_blank" rel="noopener" style={{ color: "inherit" }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
        <Typography variant="caption" color="text.secondary">
          {label}
        </Typography>
        <IconButton color="inherit" size="small" sx={{ pl: 0.5 }}>
          <OpenInNewIcon sx={{ fontSize: "0.8rem", color: "text.secondary" }} />
        </IconButton>
      </Box>
    </Link>
  );
}

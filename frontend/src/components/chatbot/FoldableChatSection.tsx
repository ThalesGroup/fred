import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import { Box, Button, Collapse, Typography } from "@mui/material";
import { SxProps, Theme } from "@mui/material/styles";
import { ReactNode, useState } from "react";

interface FoldableChatSectionProps {
  title: string;
  icon: ReactNode;
  children?: ReactNode;
  defaultOpen?: boolean;
  sx?: SxProps<Theme>;
}

export default function FoldableChatSection({
  title,
  icon,
  children,
  defaultOpen = false,
  sx,
}: FoldableChatSectionProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <Box width="100%" sx={sx}>
      <Button
        onClick={() => setOpen((v) => !v)}
        sx={{
          padding: 0,
          textTransform: "none",
          display: "flex",
          alignItems: "center",
          "&:hover": { bgcolor: "transparent" },
        }}
        disableRipple
      >
        {icon}
        <Typography variant="body2" fontWeight="medium" color="text.secondary" sx={{ ml: 1 }}>
          {title}
        </Typography>
        <ExpandMoreIcon
          sx={{
            ml: 0.5,
            transform: open ? "rotate(180deg)" : "rotate(0deg)",
            transition: "transform 0.3s",
            color: "text.secondary",
          }}
          fontSize="small"
        />
      </Button>
      <Collapse in={open} timeout={300} unmountOnExit sx={{ p: 1 }}>
        {children}
      </Collapse>
    </Box>
  );
}

import { Box } from "@mui/material";
import { ReactNode } from "react";

interface MarkdownContainerProps {
  children: ReactNode;
  padding?: number;
}

export default function MarkdownContainer({ children, padding = 3 }: MarkdownContainerProps) {
  return (
    <Box
      sx={{
        flex: 1,
        width: "100%",
        boxSizing: "border-box",
        overflowY: "auto",
        overflowX: "hidden",
        p: padding,
      }}
    >
      {children}
    </Box>
  );
}

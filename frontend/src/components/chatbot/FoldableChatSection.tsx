// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

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

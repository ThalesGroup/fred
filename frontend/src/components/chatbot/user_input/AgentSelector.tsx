import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import KeyboardArrowUpIcon from "@mui/icons-material/KeyboardArrowUp";
import { Box, BoxProps, Button, List, ListItemButton, Popover, Typography, useTheme } from "@mui/material";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { AnyAgent } from "../../../common/agent";
import { AgentChipWithIcon } from "../../../common/AgentChip";
import { DetailedTooltip } from "../../../shared/ui/tooltips/Tooltips";
export type AgentSelectorProps = AgentPopoverPickerProps & Pick<BoxProps, "sx">;

export function AgentSelector({ sx, currentAgent, agents, onSelectNewAgent }: AgentSelectorProps) {
  const theme = useTheme();
  const { t } = useTranslation();

  const [anchorEl, setAnchorEl] = useState<HTMLButtonElement | null>(null);
  const handleOpen = (event: React.MouseEvent<HTMLButtonElement>) => {
    setAnchorEl(event.currentTarget);
  };
  const handleClose = () => {
    setAnchorEl(null);
  };
  const isPickerOpen = Boolean(anchorEl);

  return (
    <>
      {/* Current agent name */}
      <Box
        sx={{
          border: `1px solid ${theme.palette.divider}`,
          borderRadius: "16px",
          background: theme.palette.background.paper,
          paddingX: 2,
          paddingY: 0.5,
          display: "flex",
          gap: 1,
          alignItems: "center",
          justifyContent: "center",
          ...sx,
        }}
      >
        <Typography>{t("agentSelector.sendTo")}</Typography>
        <Button
          sx={{
            color: "inherit",
            padding: 0.5,
            borderRadius: "16px",
            textTransform: "none",
            position: "relative",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            pr: 3.5, // leave room for the arrow without shifting the text
          }}
          onClick={handleOpen}
        >
          <AgentChipWithIcon agent={currentAgent} />

          <Box
            component="span"
            sx={{
              position: "absolute",
              right: 4,
              top: "50%",
              transform: "translateY(-50%)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            {isPickerOpen ? <KeyboardArrowUpIcon /> : <KeyboardArrowDownIcon />}
          </Box>
        </Button>
      </Box>

      {/* Popover to select agent */}
      <Popover
        open={isPickerOpen}
        anchorEl={anchorEl}
        onClose={handleClose}
        anchorOrigin={{
          vertical: "top",
          horizontal: "center",
        }}
        transformOrigin={{
          vertical: "bottom",
          horizontal: "center",
        }}
      >
        <AgentPopoverPicker
          currentAgent={currentAgent}
          agents={agents}
          onSelectNewAgent={(agent) => {
            handleClose();
            onSelectNewAgent(agent);
          }}
        />
      </Popover>
    </>
  );
}

export interface AgentPopoverPickerProps {
  currentAgent: AnyAgent;
  agents: AnyAgent[];
  onSelectNewAgent: (flow: AnyAgent) => void;
}

export function AgentPopoverPicker({ currentAgent, agents, onSelectNewAgent }: AgentPopoverPickerProps) {
  return (
    <List>
      {agents.map((agent) => {
        const tooltipDescription = [agent.tuning.role, agent.tuning.description].filter(Boolean).join("\n");
        return (
          <DetailedTooltip key={agent.id} label={agent.name} description={tooltipDescription} placement="right">
            <ListItemButton onClick={() => onSelectNewAgent(agent)} selected={agent.id === currentAgent.id}>
              <AgentChipWithIcon agent={agent} />
            </ListItemButton>
          </DetailedTooltip>
        );
      })}
    </List>
  );
}

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

import { Button, Grid2, IconButton, Tooltip, Typography } from "@mui/material";
import React from "react";

export const NestedButton = (props: {
  value: string;
  activate: boolean;
  handleClickPrimaryButton: () => void;
  handleClickSecondaryButton: () => void;
  secondaryButtonIcon: React.ReactNode;
  primaryButtonTooltip?: string;
  secondaryButtonTooltip?: string;
}) => {
  return (
    <Grid2
      container
      alignItems="center"
      sx={{
        border: props.activate ? "solid" : "",
        borderWidth: props.activate ? "2px" : "",
        borderColor: props.activate ? "primary.light" : "",
        borderRadius: 1,
      }}
    >
      <Grid2 size={10}>
        <Tooltip title={props.primaryButtonTooltip} placement="left">
          <Button
            onClick={props.handleClickPrimaryButton}
            sx={{
              width: "100%",
              textTransform: "none",
              justifyContent: "start",
            }}
          >
            <Typography color="text.primary">{props.value}</Typography>
          </Button>
        </Tooltip>
      </Grid2>
      <Grid2 size={2} display="flex" justifyContent="center">
        <Tooltip title={props.secondaryButtonTooltip} placement="left">
          <IconButton sx={{ color: "primary.light" }} onClick={props.handleClickSecondaryButton}>
            {props.secondaryButtonIcon}
          </IconButton>
        </Tooltip>
      </Grid2>
    </Grid2>
  );
};

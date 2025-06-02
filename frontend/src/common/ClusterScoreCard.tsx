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

import { Box, Button, Typography } from "@mui/material";
import { ImageComponent } from "../utils/image.tsx";
import { ClusterOverview } from "../frugalit/slices/api.tsx";

export const ClusterScoreCard = (props: {
  scope: ClusterOverview;
  handleUpdateSelectedScopes: (scopeDetail: ClusterOverview) => void;
  activate: boolean;
}) => {
  return (
    <Box display="flex" flexDirection="column" alignItems="center">
      <Button
        onClick={function () {
          props.handleUpdateSelectedScopes(props.scope);
        }}
        variant="contained"
        sx={{
          bgcolor: props.activate ? "primary.main" : "common.white",
          color: props.activate ? "common.white" : "common.black",
          border: `1px solid grey`,
          textTransform: "none",
        }}
      >
        <ImageComponent name={props.scope.provider} width="40px" height="40px" />
        <Typography pl={1}>{props.scope.alias}</Typography>
      </Button>
    </Box>
  );
};

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

import { Box, Grid2 } from "@mui/material";
import { IconComponent, KindLogoComponent } from "../../utils/image";
import { LabelValuePair } from "../../contrib/LabelValuePair";

interface ResourceIdentityCardProps {
  resource_name: string;
  resource_namespace: string;
  resource_kind: string;
  resource_id: string;
}
// ResourceIdentityCard component. It display a card with the resource name, namespace, kind, and ID.
export const ResourceIdentityCard = ({
  resource_name,
  resource_kind,
  resource_id,
  resource_namespace,
}: ResourceIdentityCardProps) => {
  return (
    <Box
      display="flex"
      flexDirection="row" // Horizontal alignment for logo and details
      alignItems="center"
      justifyContent="flex-start" // Align everything to the left
      height="100%"
      gap={2} // Adds spacing between the logo and details
      width="100%" // Ensure it takes full width
    >
      {/* Application logo on the left */}
      <Box flexShrink={0}>
        <KindLogoComponent name={resource_kind} width="25px" height="auto" />
      </Box>
      {/* Application logo on the left */}
      <Box flexShrink={0}>
        <IconComponent name={resource_name} width="25px" height="auto" />
      </Box>

      {/* Resource details */}
      <Grid2 container spacing={3} alignItems="center" justifyContent="center" width="100%">
        <Grid2 size={{ xs: 3 }}>
          <LabelValuePair label="Name" value={resource_name} />
        </Grid2>
        <Grid2 size={{ xs: 3 }}>
          <LabelValuePair label="Namespace" value={resource_namespace} />
        </Grid2>
        <Grid2 size={{ xs: 6 }} sx={{ overflow: "visible" }}>
          <LabelValuePair label="ID" value={resource_id} />
        </Grid2>
      </Grid2>
    </Box>
  );
};

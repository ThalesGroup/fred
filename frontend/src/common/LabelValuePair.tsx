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

import { Box, Typography } from "@mui/material";

interface LabelValuePairProps {
  label: string;
  value: string;
}

export const LabelValuePair = ({ label, value }: LabelValuePairProps) => {
  return (
    <Box display="flex" flexDirection="column" alignItems="center" gap={0.5}>
      <Typography variant="caption" color="primary.light">
        {label}
      </Typography>
      <Typography variant="body2" noWrap={false} sx={{ wordWrap: "break-word" }}>
        {value}
      </Typography>
    </Box>
  );
};

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
import { LogoComponent } from "./image.tsx";

interface AppCardProps {
  guessed_application: string;
}

export const ApplicationCard = ({ guessed_application }: AppCardProps) => {
  return (
    <Box p={0} paddingTop={1} display="flex" flexDirection="column" alignItems="center" justifyContent="center">
      {<LogoComponent name={guessed_application} width="30px" height="auto" />}

      <Typography align="center" fontSize={"small"} paddingTop={0} paddingBottom={1}>
        {guessed_application}
      </Typography>
    </Box>
  );
};

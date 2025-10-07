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

import ExploreIcon from "@mui/icons-material/Explore";
import { Box, Button, Typography } from "@mui/material";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

export const PageError = ({ title = "Page Not Found", message = "Resource not found" }) => {
  const navigate = useNavigate();
  const { t } = useTranslation();

  return (
    <Box height="100%" width="100%" display="flex" flexDirection="column" justifyContent="center" alignItems="center">
      <ExploreIcon
        sx={{
          fontSize: 100,
          color: "error.main",
        }}
      ></ExploreIcon>
      <Typography variant="h5" gutterBottom>
        {title}
      </Typography>
      <Typography variant="h6" gutterBottom>
        {message}
      </Typography>
      <Button variant="outlined" color="primary" onClick={() => navigate("/")}>
        {t(
        "pageError.message",
        "Back to Home."
      )}
      </Button>
    </Box>
  );
};

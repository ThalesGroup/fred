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

import { Grid2, Paper, ToggleButton, ToggleButtonGroup, Typography, useTheme } from "@mui/material";
import dayjs from "dayjs";
import utc from "dayjs/plugin/utc";
import timezone from "dayjs/plugin/timezone";
import "dayjs/locale/en-gb";
import { useContext } from "react";
import { Period } from "../../utils/period.tsx";
import { FootprintContext } from "../../app/FootprintContextProvider.tsx";

dayjs.extend(utc);
dayjs.extend(timezone);

export const PeriodPicker = () => {
  const ctx = useContext(FootprintContext);
  const theme = useTheme();
  const handlePeriodChange = (event, newPeriod) => {
    if (event && newPeriod !== null) {
      ctx.updatePeriod(newPeriod);
    }
  };

  return (
    <Grid2 container justifyContent="flex-end">
      <Paper>
        <Grid2 p={2} alignItems="center">
          <ToggleButtonGroup
            value={ctx.period}
            exclusive
            onChange={handlePeriodChange}
            sx={{
              width: "100%",
              justifyContent: "space-between",
            }}
          >
            {Object.values(Period).map((periodOption) => (
              <ToggleButton
                key={periodOption}
                value={periodOption}
                sx={{
                  flex: 1,
                  margin: "0 0.5vw",
                  padding: "0 1vw",
                  width: "auto",
                  height: "3vh",
                  border: "none",
                  textTransform: "none",
                  backgroundColor: theme.palette.text.disabled,
                  "&.Mui-selected": {
                    backgroundColor: theme.palette.primary.main,
                    borderRadius: "5px",
                  },
                  "&.Mui-disabled": {
                    backgroundColor: theme.palette.text.disabled,
                  },
                  "&:hover": {
                    backgroundColor: theme.palette.primary.main,
                    borderRadius: "5px",
                  },
                }}
              >
                <Typography variant="body2" color="primary.contrastText">
                  {periodOption}
                </Typography>
              </ToggleButton>
            ))}
          </ToggleButtonGroup>
        </Grid2>
      </Paper>
    </Grid2>
  );
};

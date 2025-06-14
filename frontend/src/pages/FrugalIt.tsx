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

import { Box, Typography, useTheme, Container, Paper, Fade, Grid2 } from "@mui/material";
import dayjs from "dayjs";
import utc from "dayjs/plugin/utc";
import timezone from "dayjs/plugin/timezone";
import "dayjs/locale/en-gb";
import { PeriodPicker } from "../frugalit/component/PeriodPicker.tsx";
import { ClusterFilter } from "../common/ClusterFilter.tsx";
import { useContext, useState, useEffect } from "react";
import { FootprintContext } from "../app/FootprintContextProvider.tsx";
import { InspectCard } from "../common/InspectCard.tsx";
import { PageBodyWrapper } from "../common/PageBodyWrapper.tsx";
import { TopBar } from "../common/TopBar.tsx";

// Import icons
import Co2Icon from "@mui/icons-material/Co2";
import EnergyIcon from "@mui/icons-material/BoltOutlined";
import MoneyIcon from "@mui/icons-material/MonetizationOnOutlined";

dayjs.extend(utc);
dayjs.extend(timezone);

export const FrugalIt = () => {
  const theme = useTheme();
  const [showElements, setShowElements] = useState(false);
  const ctx = useContext(FootprintContext);

  useEffect(() => {
    setShowElements(true);
  }, []);

  let costUnit = "€";
  let energyUnit = "kWh";
  let carbonUnit = "kg";

  if (ctx.allClusterFootprints?.length > 0) {
    costUnit = ctx.allClusterFootprints[0].cost.unit;
    energyUnit = ctx.allClusterFootprints[0].energy.unit;
    carbonUnit = ctx.allClusterFootprints[0].carbon.unit;
  }

  return (
    <PageBodyWrapper>
      <TopBar
        title="Footprint Overview"
        description="Monitor and analyze your clusters' cost, carbon, and energy metrics"
      >
        <Fade in={showElements} timeout={1500}>
          <Paper
            elevation={2}
            sx={{
              p: 3,
              borderRadius: 2,
              border: `1px solid ${theme.palette.divider}`,
              transition: "all 0.3s ease-in-out",
              "&:hover": {
                boxShadow: theme.shadows[4],
              },
            }}
          >
            <Typography variant="h6" fontWeight="bold" gutterBottom>
              Select Time Period
            </Typography>
            <PeriodPicker />
          </Paper>
        </Fade>
      </TopBar>

      {/* Main Section */}
      <Container maxWidth="xl" sx={{ height: "calc(100vh - 250px)", overflow: "auto", pb: 3 }}>
        <Grid2 container spacing={3} sx={{ height: "100%" }}>
          {/* Cluster Selection */}
          <Grid2 size={{ xs: 12, md: 3 }} sx={{ height: "100%" }}>
            <Paper
              elevation={2}
              sx={{
                p: 3,
                height: "100%",
                width: "100%",
                display: "flex",
                flexDirection: "column",
                border: `1px solid ${theme.palette.divider}`,
              }}
            >
              <Typography variant="h6" fontWeight="bold" mb={2}>
                Cluster Selection
              </Typography>
              <Box sx={{ flexGrow: 1 }}>
                <ClusterFilter />
              </Box>
            </Paper>
          </Grid2>

          {/* Total Charges */}
          <Grid2 size={{ xs: 12, md: 3 }} sx={{ height: "100%" }}>
            <Paper
              elevation={2}
              sx={{
                p: 3,
                height: "100%",
                width: "100%",
                display: "flex",
                flexDirection: "column",
                border: `1px solid ${theme.palette.divider}`,
              }}
            >
              <Box display="flex" alignItems="center" mb={2}>
                <MoneyIcon color="primary" sx={{ mr: 1 }} />
                <Typography variant="h6" fontWeight="bold">
                  Total Charges
                </Typography>
              </Box>
              <Box sx={{ flexGrow: 1 }}>
                <InspectCard
                  title=""
                  logo="cost_circle"
                  clusters={ctx.selectedClusterFootprints?.map((c) => ({
                    alias: c.cluster.alias,
                    fullname: c.cluster.fullname,
                    value: c.cost.value,
                  }))}
                  unit={costUnit}
                />
              </Box>
            </Paper>
          </Grid2>

          {/* Estimated Carbon Footprint */}
          <Grid2 size={{ xs: 12, md: 3 }} sx={{ height: "100%" }}>
            <Paper
              elevation={2}
              sx={{
                p: 3,
                height: "100%",
                width: "100%",
                display: "flex",
                flexDirection: "column",
                border: `1px solid ${theme.palette.divider}`,
              }}
            >
              <Box display="flex" alignItems="center" mb={2}>
                <Co2Icon color="error" sx={{ mr: 1 }} />
                <Typography variant="h6" fontWeight="bold">
                  Estimated Carbon Footprint
                </Typography>
              </Box>
              <Box sx={{ flexGrow: 1 }}>
                <InspectCard
                  title=""
                  logo="carbon_circle"
                  clusters={ctx.selectedClusterFootprints?.map((c) => ({
                    alias: c.cluster.alias,
                    fullname: c.cluster.fullname,
                    value: c.carbon.value,
                  }))}
                  unit={carbonUnit}
                />
              </Box>
            </Paper>
          </Grid2>

          {/* Estimated Energy Footprint */}
          <Grid2 size={{ xs: 12, md: 3 }} sx={{ height: "100%" }}>
            <Paper
              elevation={2}
              sx={{
                p: 3,
                height: "100%",
                width: "100%",
                display: "flex",
                flexDirection: "column",
                border: `1px solid ${theme.palette.divider}`,
              }}
            >
              <Box display="flex" alignItems="center" mb={2}>
                <EnergyIcon color="warning" sx={{ mr: 1 }} />
                <Typography variant="h6" fontWeight="bold">
                  Estimated Energy Footprint
                </Typography>
              </Box>
              <Box sx={{ flexGrow: 1 }}>
                <InspectCard
                  title=""
                  logo="energy_circle"
                  clusters={ctx.selectedClusterFootprints?.map((c) => ({
                    alias: c.cluster.alias,
                    fullname: c.cluster.fullname,
                    value: c.energy.value,
                  }))}
                  unit={energyUnit}
                />
              </Box>
            </Paper>
          </Grid2>
        </Grid2>
      </Container>
    </PageBodyWrapper>
  );
};

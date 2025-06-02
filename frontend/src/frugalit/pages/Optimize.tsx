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

import { Box, FormControl, Grid2, InputLabel, MenuItem, Select, useTheme } from "@mui/material";
import "dayjs/locale/en-gb";
import { useContext, useEffect, useState } from "react";
import { Serie, transformClusterConsumptionToSerie } from "../../utils/serie.tsx";
import { PageBodyWrapper } from "../../common/PageBodyWrapper.tsx";
import { ApplicationContext } from "../../app/ApplicationContextProvider.tsx";
import { ChartCard } from "../../common/ChartCard.tsx";
import dayjs, { Dayjs } from "dayjs";
import {
  Detail,
  useGetCarbonConsumptionMutation,
  useGetEnergyConsumptionMutation,
  useGetEnergyMixMutation,
  useGetFinopsCostMutation,
} from "../slices/api.tsx";
import { OptimizeGainCard } from "../../common/OptimizeGainCard.tsx";
import { LocalizationProvider } from "@mui/x-date-pickers/LocalizationProvider";
import { AdapterDayjs } from "@mui/x-date-pickers/AdapterDayjs";
import { ElectricityMixChart } from "../../common/energy/ElectricityMixChart.tsx";
import { ElectricityGco2 } from "../../common/energy/ElectricityGco2.tsx";
import { useSearchParams } from "react-router-dom";
import LoadingWithProgress from "../../components/LoadingWithProgress.tsx";
import { TopBar } from "../../common/TopBar.tsx";

enum Delta {
  DAY = "day",
  WEEK = "week",
  MONTH = "month",
  YEAR = "year",
}

// Function to get the start and end date of the previous month
/* const getPreviousMonthDateRange = (): [Dayjs, Dayjs] => {
  const now = dayjs();
  const startOfPreviousMonth = now.subtract(1, 'month').startOf('month');
  const endOfPreviousMonth = now.subtract(1, 'month').endOf('month');
  return [startOfPreviousMonth, endOfPreviousMonth];
}; */
export const Optimize = () => {
  const [searchParams] = useSearchParams();
  const clusterFullName = searchParams.get("cluster");
  const theme = useTheme();
  const application_context = useContext(ApplicationContext);
  const currentClusterOverview = application_context.currentClusterOverview;
  const now = dayjs();
  const oneMonthAgo = now.subtract(1, "month");
  const start = oneMonthAgo;
  const end = now;
  const [selectedDelta, setSelectedDelta] = useState<string>(Delta.MONTH);
  const [chartRange, setChartRange] = useState<"current" | "previous">("current"); // New state for selecting chart range

  // Add loading state for each data type
  const [, setLoadingFinops] = useState(true);
  const [, setLoadingCarbon] = useState(true);
  const [, setLoadingEnergy] = useState(true);
  const [getFinopsCost] = useGetFinopsCostMutation();
  const [getEnergyConsumption] = useGetEnergyConsumptionMutation();
  const [getCarbonConsumption] = useGetCarbonConsumptionMutation();
  const [getEnergyMix] = useGetEnergyMixMutation();

  const [lastFinops, setLastFinops] = useState<Serie | undefined>(undefined);
  const [newFinops, setNewFinops] = useState<Serie | undefined>(undefined);
  const [lastEnergy, setLastEnergy] = useState<Serie | undefined>(undefined);
  const [newEnergy, setNewEnergy] = useState<Serie | undefined>(undefined);
  const [lastCarbon, setLastCarbon] = useState<Serie | undefined>(undefined);
  const [newCarbon, setNewCarbon] = useState<Serie | undefined>(undefined);

  const [energyMixTimestamps, setEnergyMixTimestamps] = useState<string[]>([]);
  const [energyMixDetails, setEnergyMixDetails] = useState<Detail[]>([]);
  const [previousEnergyMixTimestamps, setPreviousEnergyMixTimestamps] = useState<string[]>([]);
  const [previousEnergyMixDetails, setPreviousEnergyMixDetails] = useState<Detail[]>([]);

  const fetchEnergyMix = async (start: Dayjs, end: Dayjs, delta: Delta) => {
    if (
      application_context &&
      application_context.currentClusterOverview &&
      start &&
      end &&
      application_context.currentPrecision
    ) {
      // Fetch current range data
      const energyMixResponse = await getEnergyMix({
        start: start.toISOString(),
        end: end.toISOString(),
        cluster: application_context.currentClusterOverview.alias,
        precision: application_context.currentPrecision,
      });
      if ("error" in energyMixResponse) {
        console.error(energyMixResponse.error);
      } else {
        const { timestamps, details } = energyMixResponse.data;
        setEnergyMixTimestamps(timestamps);
        setEnergyMixDetails(details);
      }

      // Fetch previous range data
      const previousStart = start.subtract(1, delta).subtract(end.diff(start, "day"), "day");
      const previousEnd = start.subtract(1, delta);

      const previousEnergyMixResponse = await getEnergyMix({
        start: previousStart.toISOString(),
        end: previousEnd.toISOString(),
        cluster: application_context.currentClusterOverview.alias,
        precision: application_context.currentPrecision,
      });

      if ("error" in previousEnergyMixResponse) {
        console.error(previousEnergyMixResponse.error);
      } else {
        const { timestamps, details } = previousEnergyMixResponse.data;
        setPreviousEnergyMixTimestamps(timestamps);
        setPreviousEnergyMixDetails(details);
      }
    }
  };
  const fetchData = (
    start: Dayjs,
    end: Dayjs,
    delta: Delta,
    setNewData: (serie: Serie) => void,
    setLastData: (serie: Serie) => void,
    newDataColor: string,
    lastDataColor: string,
    newDataName: string,
    lastDataName: string,
    getData: (params: {
      start: string;
      end: string;
      cluster: string;
      precision: string;
    }) => Promise<{ data: any } | { error: any }>,
    setLoading: (loading: boolean) => void, // pass loading state handler
  ) => {
    if (
      application_context &&
      application_context.currentClusterOverview &&
      start &&
      end &&
      application_context.currentPrecision
    ) {
      setNewData(undefined);
      setLastData(undefined);
      setLoading(true); // Start loading

      getData({
        start: start.toISOString(),
        end: end.toISOString(),
        cluster: application_context.currentClusterOverview.alias,
        precision: application_context.currentPrecision,
      }).then((response) => {
        if ("error" in response) {
          console.error(response.error);
        } else {
          setNewData(transformClusterConsumptionToSerie(response.data, newDataName, newDataColor));
        }
        setLoading(false); // End loading
      });

      getData({
        start: start.subtract(1, delta).subtract(end.diff(start, "day"), "day").toISOString(),
        end: start.subtract(1, delta).toISOString(),
        cluster: application_context.currentClusterOverview.alias,
        precision: application_context.currentPrecision,
      }).then((response) => {
        if ("error" in response) {
          console.error(response.error);
        } else {
          setLastData(transformClusterConsumptionToSerie(response.data, lastDataName, lastDataColor));
        }
        setLoading(false); // End loading
      });
    }
  };

  /* const handleDateChange = (newRange: [Dayjs | null, Dayjs | null]) => {
    setStart(undefined);
    setEnd(undefined);
    setStart(newRange[0]);
    setEnd(newRange[1]);
  }; */

  // Check if the current cluster overview is available and the alias matches the clusterName
  // If not, navigate to the correct cluster overview page. This is typically used to sync the URL
  // with the current cluster overview in the application context  after a side bar change.
  useEffect(() => {
    if (currentClusterOverview?.fullname !== clusterFullName) {
      application_context.fetchClusterAndNamespaceData(clusterFullName);
    }
  }, [clusterFullName, currentClusterOverview]);

  useEffect(() => {
    if (start && end) {
      fetchData(
        start,
        end,
        selectedDelta as Delta,
        setNewFinops,
        setLastFinops,
        theme.palette.chart.highBlue,
        theme.palette.chart.lowBlue,
        "Current charges",
        "Previous charges",
        getFinopsCost,
        setLoadingFinops,
      );
      fetchData(
        start,
        end,
        selectedDelta as Delta,
        setNewCarbon,
        setLastCarbon,
        theme.palette.chart.veryHighGreen,
        theme.palette.chart.mediumGreen,
        "Current carbon",
        "Previous carbon",
        getCarbonConsumption,
        setLoadingCarbon,
      );
      fetchData(
        start,
        end,
        selectedDelta as Delta,
        setNewEnergy,
        setLastEnergy,
        theme.palette.chart.veryHighYellow,
        theme.palette.chart.mediumYellow,
        "Current energy",
        "Previous energy",
        getEnergyConsumption,
        setLoadingEnergy,
      );
      fetchEnergyMix(start, end, selectedDelta as Delta);
    }
  }, [start, end, application_context.currentClusterOverview, selectedDelta, application_context.currentPrecision]);

  const handleChange = (event) => {
    setSelectedDelta(event.target.value);
  };
  if (!currentClusterOverview || currentClusterOverview?.fullname !== clusterFullName) {
    return (
      <PageBodyWrapper>
        <LoadingWithProgress />
      </PageBodyWrapper>
    );
  }
  return (
    <PageBodyWrapper>
      <TopBar title="Optimize" description="Optimize your cloud resources" backgroundUrl="" leftLg={4}>
        <Grid2 container size={12} alignItems="center" justifyContent="space-between">
          <Grid2 size={{ xs: 3, sm: 3, md: 3, lg: 3, xl: 3 }} display="flex" justifyContent="flex-start">
            {/* First item (aligned to the left) */}
            <LocalizationProvider dateAdapter={AdapterDayjs}>
              {/* 
              <DateRangePicker
                value={[start, end]}
                onChange={handleDateChange}
              />
              */}
            </LocalizationProvider>
          </Grid2>

          <Grid2 size={{ xs: 3, sm: 3, md: 3, lg: 3, xl: 3 }} display="flex" justifyContent="center">
            {/* Second item (centered) */}
            <Select value={selectedDelta} label="Delta" onChange={handleChange}>
              {Object.values(Delta).map((delta) => (
                <MenuItem key={delta} value={delta}>
                  {delta}
                </MenuItem>
              ))}
            </Select>
          </Grid2>

          <Grid2 size={{ xs: 3, sm: 3, md: 3, lg: 3, xl: 2 }} display="flex" justifyContent="flex-end">
            {/* Fourth item (aligned to the right) */}
            <FormControl variant="outlined" sx={{ minWidth: 120, borderColor: theme.palette.primary.main }}>
              <InputLabel id="select-chart-range-label" sx={{ color: theme.palette.text.primary }}>
                Range
              </InputLabel>
              <Select
                labelId="select-chart-range-label"
                value={chartRange}
                label="Range"
                onChange={(e) => setChartRange(e.target.value as "current" | "previous")}
                sx={{
                  "& .MuiOutlinedInput-notchedOutline": {
                    borderColor: theme.palette.text.primary,
                  },
                  "&:hover .MuiOutlinedInput-notchedOutline": {
                    borderColor: theme.palette.text.primary,
                  },
                  "& .MuiSvgIcon-root": {
                    color: theme.palette.text.primary,
                  },
                  // Ensure the InputLabel color is inherited properly
                  "& .MuiInputLabel-root": {
                    color: theme.palette.text.primary,
                  },
                }}
              >
                <MenuItem value="current">Current Range</MenuItem>
                <MenuItem value="previous">Previous Range</MenuItem>
              </Select>
            </FormControl>
          </Grid2>
        </Grid2>
      </TopBar>
      <Grid2 container size={12} spacing={4} p={2}>
        <Grid2 container size={12}>
          <OptimizeGainCard
            date={dayjs()}
            data={[
              {
                logos: ["cost_circle", "cost_white"],
                color: theme.palette.chart.blue,
                series: newFinops && lastFinops ? [newFinops, lastFinops] : [],
              },
              {
                logos: ["carbon_circle", "carbon_white"],
                color: theme.palette.chart.green,
                series: newCarbon && lastCarbon ? [newCarbon, lastCarbon] : [],
              },
              {
                logos: ["energy_circle", "energy_white"],
                color: theme.palette.chart.yellow,
                series: newEnergy && lastEnergy ? [newEnergy, lastEnergy] : [],
              },
            ]}
          />
        </Grid2>
        <Grid2 size={{ xs: 12 }}>
          <Box width="100%">
            <ChartCard
              data={{
                name: "FinOps",
                color: "primary.main",
                unit: "cm",
                serieTypes: [
                  {
                    logos: ["cost_circle", "cost_white"],
                    color: theme.palette.chart.highBlue,
                    series: newFinops && lastFinops ? [newFinops, lastFinops] : [],
                  },
                  {
                    logos: ["carbon_circle", "carbon_white"],
                    color: theme.palette.chart.highGreen,
                    series: newCarbon && lastCarbon ? [newCarbon, lastCarbon] : [],
                  },
                  {
                    logos: ["energy_circle", "energy_white"],
                    color: theme.palette.chart.highYellow,
                    series: newEnergy && lastEnergy ? [newEnergy, lastEnergy] : [],
                  },
                ],
              }}
              height="20vh"
              type="bar"
            />
          </Box>

          <Grid2 size={{ xs: 12 }}>
            <Box pt={1} width="100%">
              {/* Conditionally render the ElectricityMixChart based on chartRange selection */}
              {chartRange === "current" ? (
                <ElectricityMixChart
                  timestamps={energyMixTimestamps}
                  details={energyMixDetails}
                  precision={"hourly"}
                  height="200px"
                />
              ) : (
                <ElectricityMixChart
                  timestamps={previousEnergyMixTimestamps}
                  details={previousEnergyMixDetails}
                  precision={"hourly"}
                  height="200px"
                />
              )}
            </Box>
            <Box pt={1} width="100%">
              {chartRange === "current" ? (
                <ElectricityGco2
                  timestamps={energyMixTimestamps}
                  details={energyMixDetails}
                  precision={"hourly"}
                  height="200px"
                />
              ) : (
                <ElectricityGco2
                  timestamps={previousEnergyMixTimestamps}
                  details={previousEnergyMixDetails}
                  precision={"hourly"}
                  height="200px"
                />
              )}
            </Box>
          </Grid2>
        </Grid2>
      </Grid2>
    </PageBodyWrapper>
  );
};

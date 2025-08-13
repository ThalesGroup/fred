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
import { ChartCard } from "../../contrib/ChartCard.tsx";
import dayjs, { Dayjs } from "dayjs";
import {
  Detail,
  useGetCarbonConsumptionMutation,
  useGetEnergyConsumptionMutation,
  useGetEnergyMixMutation,
  useGetFinopsCostMutation,
} from "../slices/api.tsx";
import { OptimizeGainCard } from "../../contrib/OptimizeGainCard.tsx";
import { LocalizationProvider } from "@mui/x-date-pickers/LocalizationProvider";
import { AdapterDayjs } from "@mui/x-date-pickers/AdapterDayjs";
import { ElectricityMixChart } from "../../contrib/energy/ElectricityMixChart.tsx";
import { ElectricityGco2 } from "../../contrib/energy/ElectricityGco2.tsx";
import { useSearchParams } from "react-router-dom";
import LoadingWithProgress from "../../components/LoadingWithProgress.tsx";
import { TopBar } from "../../common/TopBar.tsx";
import { DatePicker } from "@mui/x-date-pickers/DatePicker";
import { K8ApplicationContext } from "../../app/K8ApplicationContextProvider.tsx";

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
  const application_context = useContext(K8ApplicationContext);
  const currentClusterOverview = application_context.currentClusterOverview;
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

  const today = dayjs();
  const startOfThisMonth = today.startOf("month");

  // Use last full month as "current", and the one before as "previous"
  const defaultCurrentMonth = startOfThisMonth.subtract(1, "month"); // e.g. May if now is June
  const defaultPreviousMonth = startOfThisMonth.subtract(2, "month"); // e.g. April if now is June

  const [currentMonth, setCurrentMonth] = useState<Dayjs | null>(defaultCurrentMonth);
  const [previousMonth, setPreviousMonth] = useState<Dayjs | null>(defaultPreviousMonth);

  const [selectedDelta] = useState<Delta>(Delta.MONTH);

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
  const fetchData = async (
    start: Dayjs,
    end: Dayjs,
    name: string,
    color: string,
    getData: (params: {
      start: string;
      end: string;
      cluster: string;
      precision: string;
    }) => Promise<{ data: any } | { error: any }>,
    setData: (serie: Serie) => void,
    setLoading: (loading: boolean) => void,
  ) => {
    if (application_context.currentClusterOverview && application_context.currentPrecision) {
      setLoading(true);
      const response = await getData({
        start: start.toISOString(),
        end: end.toISOString(),
        cluster: application_context.currentClusterOverview.alias,
        precision: application_context.currentPrecision,
      });

      if ("error" in response) {
        console.error(response.error);
      } else {
        setData(transformClusterConsumptionToSerie(response.data, name, color));
      }
      setLoading(false);
    }
  };

  // Check if the current cluster overview is available and the alias matches the clusterName
  // If not, navigate to the correct cluster overview page. This is typically used to sync the URL
  // with the current cluster overview in the application context  after a side bar change.
  useEffect(() => {
    if (currentClusterOverview?.fullname !== clusterFullName) {
      application_context.fetchClusterAndNamespaceData(clusterFullName);
    }
  }, [clusterFullName, currentClusterOverview]);

  useEffect(() => {
    if (
      currentMonth &&
      previousMonth &&
      application_context.currentClusterOverview &&
      application_context.currentPrecision
    ) {
      const currentStart = currentMonth.startOf("month");
      const currentEnd = currentMonth.endOf("month");
      const previousStart = previousMonth.startOf("month");
      const previousEnd = previousMonth.endOf("month");

      // Current month data
      fetchData(
        currentStart,
        currentEnd,
        "Current charges",
        theme.palette.chart.veryHighBlue,
        getFinopsCost,
        setNewFinops,
        setLoadingFinops,
      );
      fetchData(
        currentStart,
        currentEnd,
        "Current carbon",
        theme.palette.chart.veryHighGreen,
        getCarbonConsumption,
        setNewCarbon,
        setLoadingCarbon,
      );
      fetchData(
        currentStart,
        currentEnd,
        "Current energy",
        theme.palette.chart.veryHighYellow,
        getEnergyConsumption,
        setNewEnergy,
        setLoadingEnergy,
      );

      // Previous month data
      fetchData(
        previousStart,
        previousEnd,
        "Previous charges",
        theme.palette.chart.mediumBlue,
        getFinopsCost,
        setLastFinops,
        setLoadingFinops,
      );
      fetchData(
        previousStart,
        previousEnd,
        "Previous carbon",
        theme.palette.chart.mediumGreen,
        getCarbonConsumption,
        setLastCarbon,
        setLoadingCarbon,
      );
      fetchData(
        previousStart,
        previousEnd,
        "Previous energy",
        theme.palette.chart.mediumYellow,
        getEnergyConsumption,
        setLastEnergy,
        setLoadingEnergy,
      );

      // Energy mix (only for current range)
      fetchEnergyMix(currentStart, currentEnd, selectedDelta as Delta);
    }
  }, [currentMonth, previousMonth, application_context.currentClusterOverview, application_context.currentPrecision]);

  //const handleChange = (event) => {
  //  setSelectedDelta(event.target.value);
  //};
  if (!currentClusterOverview || currentClusterOverview?.fullname !== clusterFullName) {
    return <LoadingWithProgress />;
  }
  return (
    <>
      <TopBar title="Optimize" description="Optimize your cloud resources">
        <Grid2 container size={12} alignItems="center" justifyContent="space-between">
          <Grid2 size={{ xs: 4, sm: 6, md: 6, lg: 6, xl: 6 }} display="flex" justifyContent="flex-start">
            {/* First item (aligned to the left) */}
            <LocalizationProvider dateAdapter={AdapterDayjs}>
              <Grid2 display="flex" gap={1} alignItems="center">
                <Grid2>
                  <DatePicker
                    label="Current month"
                    views={["year", "month"]}
                    value={currentMonth}
                    onChange={(newValue) => setCurrentMonth(newValue)}
                    slotProps={{ textField: { size: "small" } }} // optional for compact styling
                  />
                </Grid2>
                <Grid2>
                  <DatePicker
                    label="Previous month"
                    views={["year", "month"]}
                    value={previousMonth}
                    onChange={(newValue) => setPreviousMonth(newValue)}
                    slotProps={{ textField: { size: "small" } }}
                  />
                </Grid2>
              </Grid2>
            </LocalizationProvider>
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
    </>
  );
};

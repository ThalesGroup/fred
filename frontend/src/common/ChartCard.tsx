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

import {
  Box,
  Grid2,
  MenuItem,
  Paper,
  Select,
  Skeleton,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from "@mui/material";
import BarChartIcon from "@mui/icons-material/BarChart";
import ShowChartIcon from "@mui/icons-material/ShowChart";
import dayjs from "dayjs";
import utc from "dayjs/plugin/utc";
import timezone from "dayjs/plugin/timezone";
import "dayjs/locale/en-gb";
import { getSumValue } from "../utils/serie";
import { RiftChart } from "./RiftChart";
import { ImageComponent } from "../utils/image";
import { useContext, useEffect, useState } from "react";
import { ChartSeries, SerieType } from "../utils/chartSeries";
import HorizontalRuleIcon from "@mui/icons-material/HorizontalRule";
import { DurationPrecision } from "../utils/period.tsx";
import { ApplicationContext } from "../app/ApplicationContextProvider.tsx";

dayjs.extend(utc);
dayjs.extend(timezone);

export const ChartCard = (props: { data: ChartSeries; height: string; type: string }) => {
  const ctx = useContext(ApplicationContext);
  const [chartType, setChartType] = useState("bar");
  const [chartSerieType, setChartSerieType] = useState<SerieType | undefined>(undefined);

  const handleChartTypeChange = (event, newChartType) => {
    if (event && newChartType !== null) {
      setChartType(newChartType);
    }
  };

  useEffect(() => {
    if (props.data?.serieTypes?.length > 0) {
      setChartSerieType(props.data.serieTypes[0]);
    }
  }, [props.data]);

  useEffect(() => {
    setChartType(props.type);
  }, [props.type]);

  const handleChartSerieTypeChange = (event, newChartSerieType) => {
    if (event && newChartSerieType !== null) {
      setChartSerieType(newChartSerieType);
    }
  };

  const chartOptions = ["line", "bar"];

  const handlePrecisionChange = (event, precision) => {
    if (event && precision) {
      ctx.updateCurrentPrecision(precision.props.value as DurationPrecision);
    }
  };

  return (
    <Grid2 size={12} container>
      <Paper sx={{ width: "100%" }}>
        <Grid2 container p={2}>
          <Grid2 size={{ xs: 12 }} justifyContent="space-between" display="flex" alignItems="center">
            <Grid2 size="auto" alignItems="center">
              {props.data?.serieTypes?.length > 0 ? (
                <ToggleButtonGroup value={chartSerieType} exclusive onChange={handleChartSerieTypeChange}>
                  {props.data.serieTypes.map((serieType) => (
                    <ToggleButton
                      value={serieType}
                      key={serieType.logos[0]}
                      sx={{
                        width: "5vw",
                        height: "3vh",
                        borderRadius: "10px",
                        borderColor: "primary.main",
                        backgroundColor: chartSerieType === serieType ? serieType.color : "paper.background",
                        color: chartSerieType === serieType ? "test.disabled" : serieType.color,
                        "&.Mui-selected": {
                          backgroundColor: serieType.color,
                        },
                      }}
                    >
                      <ImageComponent
                        name={chartSerieType === serieType ? serieType.logos[1] : serieType.logos[0]}
                        width="18px"
                        height="18px"
                      />
                    </ToggleButton>
                  ))}
                </ToggleButtonGroup>
              ) : (
                <Skeleton animation="wave" width={"115px"} height={"30px"} sx={{ justifyContent: "flex-end" }} />
              )}
            </Grid2>
            {props.data?.serieTypes[0]?.series?.length > 1
              ? chartSerieType && (
                  <Grid2 size={{ xs: 12 }} display="flex" alignItems="center" justifyContent="center">
                    {chartSerieType.series.map((serie) => (
                      <Grid2 container key={serie.name} alignItems="center">
                        <HorizontalRuleIcon sx={{ color: serie.color, ml: 1, fontSize: "5vh" }}></HorizontalRuleIcon>
                        <Typography sx={{ mr: 1 }}>
                          {serie.name} (
                          {serie.seriePoints.length > 0 && serie.seriePoints[0]?.date
                            ? dayjs(serie.seriePoints[0].date).format("DD MMM")
                            : "N/A"}{" "}
                          -{" "}
                          {serie.seriePoints.length > 0 && serie.seriePoints[serie.seriePoints.length - 1]?.date
                            ? dayjs(serie.seriePoints[serie.seriePoints.length - 1].date).format("DD MMM YYYY")
                            : "N/A"}
                          )
                        </Typography>
                      </Grid2>
                    ))}
                  </Grid2>
                )
              : chartSerieType?.series?.length > 0 && (
                  <Grid2 size={{ xs: 12 }} display="flex" alignItems="center" justifyContent="center">
                    <Typography>
                      {chartSerieType.series[0].name} : {getSumValue(chartSerieType.series[0]).toLocaleString()}{" "}
                      {chartSerieType.series[0].unit}
                    </Typography>
                  </Grid2>
                )}
            <Grid2 size="auto" mr={2}>
              <Select
                value={ctx.currentPrecision}
                label="Precision"
                onChange={handlePrecisionChange}
                sx={{
                  //  width: '5vw',
                  height: "3vh",
                  display: "flex",
                  borderWidth: "1px", // Adjust the width of the border
                  ".MuiOutlinedInput-notchedOutline": {
                    // This targets the inner outline border
                    borderWidth: "1px", // Adjust the inner border width here
                    borderColor: "primary.main", // Adjust the inner border color
                  },
                }}
              >
                {Object.values(DurationPrecision).map((precision) => (
                  <MenuItem key={precision} value={precision}>
                    {precision}
                  </MenuItem>
                ))}
              </Select>
            </Grid2>
            <Grid2 size="auto" display="flex" alignItems="center">
              {props.data?.serieTypes?.length > 0 ? (
                <ToggleButtonGroup value={chartType} exclusive onChange={handleChartTypeChange}>
                  {chartOptions.map((chartOption) => (
                    <ToggleButton
                      value={chartOption}
                      key={chartOption}
                      sx={{
                        width: "4vw",
                        height: "3vh",
                        borderColor: "primary.main",
                        backgroundColor: chartType === chartOption ? "primary.main" : "text.disabled",
                        color: "primary.contrastText",
                        "&.Mui-selected": {
                          backgroundColor: "primary.main",
                          color: "primary.contrastText",
                        },
                      }}
                    >
                      {chartOption === "bar" ? <BarChartIcon /> : <ShowChartIcon />}
                    </ToggleButton>
                  ))}
                </ToggleButtonGroup>
              ) : (
                <Skeleton animation="wave" width={"115px"} height={"30px"} sx={{ justifyContent: "flex-end" }} />
              )}
            </Grid2>
          </Grid2>
          <Grid2 size={12} pt={1}>
            <Box height={props.height}>
              {chartSerieType ? (
                <RiftChart series={chartSerieType.series} type={chartType}></RiftChart>
              ) : (
                <Skeleton animation="wave" width={"100%"} height={"100%"} />
              )}
            </Box>
          </Grid2>
        </Grid2>
      </Paper> 
    </Grid2>
  );
};

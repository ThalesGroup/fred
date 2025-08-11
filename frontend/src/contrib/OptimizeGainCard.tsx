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

import { Divider, Grid2, Paper, Typography, useMediaQuery, useTheme } from "@mui/material";
import dayjs, { Dayjs } from "dayjs";
import utc from "dayjs/plugin/utc";
import timezone from "dayjs/plugin/timezone";
import "dayjs/locale/en-gb";
import UpIcon from "@mui/icons-material/NorthEastOutlined";
import DownIcon from "@mui/icons-material/SouthEastOutlined";
import React from "react";
import { ImageComponent } from "../utils/image.tsx";
import { SerieType } from "../utils/chartSeries.tsx";
import { getSumValue } from "../utils/serie.tsx";
import ViewStreamIcon from "@mui/icons-material/ViewStream";
import InsightsIcon from "@mui/icons-material/Insights";

dayjs.extend(utc);
dayjs.extend(timezone);

export const OptimizeGainCard = (props: { date: Dayjs; data: SerieType[] }) => {
  const theme = useTheme();
  const isLargeScreen = useMediaQuery(theme.breakpoints.up("lg"));

  const getPercentage = (serieType: SerieType) => {
    if (serieType.series.length > 1) {
      return (
        ((getSumValue(serieType.series[0]) - getSumValue(serieType.series[1])) * 100) / getSumValue(serieType.series[1])
      );
    } else {
      return 0;
    }
  };

  const getDiff = (serieType: SerieType) => {
    if (serieType.series.length > 1) {
      return getSumValue(serieType.series[0]) - getSumValue(serieType.series[1]);
    } else {
      return 0;
    }
  };

  const getCorrectColor = (number: number) => {
    if (number > 0) {
      return theme.palette.chart.highYellow;
    } else if (number === 0) {
      return theme.palette.chart.mediumYellow;
    } else {
      return theme.palette.chart.highGreen;
    }
  };

  const getIcon = (serieType: SerieType) => {
    const iconSize = "40px"; // Adjust the size here as needed

    if (getPercentage(serieType) > 0) {
      return (
        <UpIcon
          sx={{
            color: getCorrectColor(getPercentage(serieType)),
            fontSize: iconSize,
          }}
        />
      );
    } else if (getPercentage(serieType) === 0) {
      return (
        <ViewStreamIcon
          sx={{
            color: getCorrectColor(getPercentage(serieType)),
            fontSize: iconSize,
          }}
        />
      );
    } else {
      return (
        <DownIcon
          sx={{
            color: getCorrectColor(getPercentage(serieType)),
            fontSize: iconSize,
          }}
        />
      );
    }
  };

  return (
    <Grid2 container size={12}>
      <Paper sx={{ width: "100%", display: "flex" }}>
        {isLargeScreen ? (
          <>
            <Grid2 container size={3} sx={{ justifyContent: "center" }}>
              <Grid2
                size={12}
                p={3}
                sx={{
                  display: "flex",
                  justifyContent: "center",
                  height: "6vh",
                  alignItems: "center",
                }}
              >
                <InsightsIcon sx={{ width: "30px", height: "30px" }} />
                <Typography variant="h5" sx={{ paddingLeft: 1 }}>
                  Gain insights
                </Typography>
              </Grid2>
              <Divider
                sx={{
                  borderWidth: 1,
                  borderColor: theme.palette.primary.light,
                  width: "90%",
                }}
              ></Divider>
              <Grid2
                size={12}
                sx={{
                  display: "flex",
                  justifyContent: "center",
                  height: "6vh",
                  alignItems: "center",
                }}
              >
                <Typography variant="body1">{props.date.utc().format("DD/MM/YYYY")}</Typography>
              </Grid2>
            </Grid2>
            <Divider
              orientation="vertical"
              flexItem
              sx={{
                borderWidth: 0.5,
                borderColor: theme.palette.primary.light,
                height: "80%",
                alignSelf: "center",
                marginX: 2,
              }}
            />
          </>
        ) : (
          <></>
        )}

        <Grid2 container size={isLargeScreen ? 9 : 12} sx={{ justifyContent: "center" }}>
          <Grid2
            size={12}
            sx={{
              display: "flex",
              justifyContent: "center",
              height: "12vh",
              alignItems: "center",
            }}
          >
            {props.data?.length > 0 &&
              props.data.map((serieType, index) => (
                <React.Fragment key={index}>
                  <Grid2
                    size={4}
                    sx={{
                      display: "flex",
                      justifyContent: "center",
                      alignItems: "center",
                    }}
                  >
                    <ImageComponent name={serieType.logos[0]} width="30px" height="30px" />
                    <Grid2 sx={{ display: "row", paddingLeft: 2, paddingRight: 2 }}>
                      <Typography
                        variant="h5"
                        sx={{
                          color: getCorrectColor(getPercentage(serieType)),
                          paddingLeft: 1,
                        }}
                      >
                        {getPercentage(serieType).toFixed(2)} %
                      </Typography>
                      <Typography variant="h6" sx={{ paddingLeft: 1 }}>
                        {getDiff(serieType) > 0 && "+"} {getDiff(serieType)}{" "}
                        {serieType.series.length > 0 && serieType.series[0].unit}
                      </Typography>
                    </Grid2>
                    {getIcon(serieType)}
                  </Grid2>
                  {index < props.data.length - 1 && (
                    <Divider
                      orientation="vertical"
                      flexItem
                      sx={{
                        borderWidth: 0.5,
                        borderColor: theme.palette.primary.light,
                        height: "80%",
                        alignSelf: "center",
                        marginX: 2,
                      }}
                    />
                  )}
                </React.Fragment>
              ))}
          </Grid2>
        </Grid2>
      </Paper>
    </Grid2>
  );
};

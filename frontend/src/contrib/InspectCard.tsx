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
  Grid2,
  Typography,
  Paper,
  Divider,
  ToggleButtonGroup,
  ToggleButton,
  Box,
  TableContainer,
  Table,
  TableHead,
  TableRow,
  TableCell,
  TableBody,
  useTheme,
} from "@mui/material";
import dayjs from "dayjs";
import utc from "dayjs/plugin/utc";
import timezone from "dayjs/plugin/timezone";
import "dayjs/locale/en-gb";
import { useContext, useState } from "react";
import { ImageComponent } from "../utils/image";
import { PieChart } from "./PieChart";
import { ApplicationContext } from "../app/ApplicationContextProvider";

dayjs.extend(utc);
dayjs.extend(timezone);

interface InspectCardProps {
  title: string;
  logo: string;
  clusters: { alias: string; fullname: string; value: number }[];
  unit: string;
}
export const InspectCard = ({ title, logo, clusters, unit }: InspectCardProps) => {
  useContext(ApplicationContext);
  const theme = useTheme();
  const [chart, setChart] = useState("pie");

  const handleChartSerieChange = (event, chartOption) => {
    if (event && chartOption !== null) {
      setChart(chartOption);
    }
  };
  const chartOptions = ["table", "pie"];
  return (
    <Box p={2} sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <Grid2 container justifyContent="center" alignItems="center" spacing={2}>
        {/* Logo */}
        <Grid2 size={2} container justifyContent="left">
          <Box display="flex" justifyContent="center">
            <ImageComponent name={logo} width="4vh" height="auto" />
          </Box>
        </Grid2>

        {/* Sum */}
        <Grid2 size={5} container justifyContent="right">
          <Typography variant="h5" align="center">
            {clusters
              .map((cluster) => cluster.value)
              .reduce((sum, value) => sum + value, 0)
              .toLocaleString()}{" "}
            {unit}
          </Typography>
        </Grid2>

        {/* Title */}
        <Grid2 size={5} container justifyContent="right">
          <Typography align="center">{title}</Typography>
        </Grid2>
      </Grid2>
      {clusters.length > 0 && (
        <Box sx={{ flexGrow: 1, display: "flex", flexDirection: "column" }}>
          <Grid2 container size={{ xs: 12 }} sx={{ pt: 1 }} direction="column">
            <Grid2 container size={{ xs: 12 }} justifyContent="center">
              <Divider
                sx={{
                  width: "100%",
                  borderWidth: 1,
                  borderColor: theme.palette.primary.light,
                }}
              />
            </Grid2>
            <Grid2 size={{ xs: 12 }}>
              <Grid2 pt={1}>
                <Grid2 container size={{ xs: 12 }} justifyContent="flex-end" pr={2}>
                  <ToggleButtonGroup value={chart} exclusive onChange={handleChartSerieChange}>
                    {chartOptions.map((chartOption) => (
                      <ToggleButton
                        value={chartOption}
                        key={chartOption}
                        sx={{
                          width: "50px",
                          height: "24px",
                          borderRadius: "10px",
                          backgroundColor:
                            chartOption === chart ? theme.palette.primary.main : theme.palette.primary.light,
                          color: chartOption === chart ? theme.palette.primary.main : theme.palette.primary.light,
                          "&.Mui-selected": {
                            backgroundColor: theme.palette.primary.main,
                          },
                        }}
                      >
                        <ImageComponent
                          name={chartOption === chart ? `${chartOption}_white` : `${chartOption}_white`}
                          width="14px"
                          height="14px"
                        />
                      </ToggleButton>
                    ))}
                  </ToggleButtonGroup>
                </Grid2>
                {chart === "pie" ? (
                  <Grid2 size={{ xs: 12 }} sx={{ pt: 1 }} justifyContent="center">
                    <Box
                      display="flex"
                      justifyContent="center" // Centers horizontally
                      alignItems="center" // Centers vertically
                      height="30vh" // Adjust height as needed
                      width="100%" // Width can be 100% of the parent container
                    >
                      <PieChart data={clusters} unit={unit} />
                    </Box>
                  </Grid2>
                ) : (
                  <Grid2 container size={{ xs: 12 }} sx={{ pt: 1 }} justifyContent="center">
                    <Box>
                      <TableContainer component={Paper} sx={{ height: "100%" }}>
                        <Table sx={{ height: "100%" }}>
                          <TableHead>
                            <TableRow>
                              <TableCell align="center">Name</TableCell>
                              <TableCell align="center">
                                {title} ({unit})
                              </TableCell>
                              <TableCell align="center">%</TableCell>
                            </TableRow>
                          </TableHead>
                          <TableBody>
                            {clusters
                              .sort((a, b) => b.value - a.value)
                              .map((cluster) => (
                                <TableRow key={cluster.alias}>
                                  <TableCell align="center">{cluster.alias}</TableCell>
                                  <TableCell align="center">{cluster.value}</TableCell>
                                  <TableCell align="center">
                                    {(
                                      (cluster.value * 100) /
                                      clusters.map((c) => c.value).reduce((sum, value) => sum + value, 0)
                                    ).toFixed(2)}
                                  </TableCell>
                                </TableRow>
                              ))}
                          </TableBody>
                        </Table>
                      </TableContainer>
                    </Box>
                  </Grid2>
                )}
              </Grid2>
            </Grid2>
          </Grid2>
        </Box>
      )}
    </Box>
  );
};

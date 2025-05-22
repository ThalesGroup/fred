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

import React from "react";
import Box from "@mui/material/Box";
import { CircularProgress, Typography, useTheme } from "@mui/material";
import ReactECharts from 'echarts-for-react';

export interface ChartOptions {
  series: Object[],
  radar: Object,
}

export const ResourceScoreSimpleRadarChart = (props: {
  data: { attribut_name: string; value: number }[];
  unit: string;
  application_name: string;
  zoom: string;
}) => {

  const theme = useTheme();
  const valuesSerie: number[] = [];
  const indicators: { name: string; max: number }[] = [];

  const transformToText = (inputString: string | null): string => {
    if (inputString !== null) {
      return inputString
          .split('_')
          .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
          .join('\n');
    }
    return '';
  };

  props.data.map((attribut) => valuesSerie.push(attribut.value));
  props.data.map((attribut) =>
      indicators.push({ name: transformToText(attribut.attribut_name), max: 100 })
  );

  const renderOptions = () => {
    if (props.data.length === 0) return {};

    const opt: ChartOptions = {
      radar: {
        radius: props.zoom,
       // center: ['50%', '50%'],
        indicator: indicators,
        name: {
          textStyle: {
            color: theme.palette.text.primary,
          }
        },
        nameGap: 5,
        scale: true,
        splitArea: { // Adds background between lines
          show: true,
          areaStyle: {
            color: [theme.palette.chart.alterningBgColor1, theme.palette.chart.alterningBgColor2] // Alternating colors for the background
          }
        }
      },
      series: [
        {
          name: 'Score of the application',
          type: 'radar',
          lineStyle: { // Customize the color of the line
            color: theme.palette.chart.secondary, // You can customize this as per your theme or preferred color
            width: 2 // Adjust line width
          },
          areaStyle: { // Adds background fill between the lines
            color: theme.palette.chart.customAreaStyle, // Custom color for the filled area
            opacity: 0.5 // Set opacity for better visual
          },
          data: [
            {
              value: valuesSerie,
              name: props.application_name
            }
          ],
          symbol: 'circle', // Shape of the point, can also be 'rect', 'diamond', 'triangle', etc.
          symbolSize: 8, // Size of the point
          itemStyle: { // Style of the point
            color: theme.palette.chart.secondary, // Color of the point
            borderColor: theme.palette.chart.primary, // Border color of the point
            borderWidth: 2 // Border width of the point
          },
          emphasis: { // Style when hovering over the point
            itemStyle: {
              color: theme.palette.error.main, // Color of the point when hovered
              borderColor: theme.palette.warning.main, // Border color when hovered
              borderWidth: 3 // Border width when hovered
            }
          }
        }
      ]
    };
    return opt;
  };

  return (
      <Box height={"100%"}>
        {props.data.length > 0 ? (
            <React.Fragment>
              <Box height={"100%"} width={"100%"}>
                <ReactECharts option={renderOptions()} style={{ height: '100%', width: '100%' }} />
              </Box>
            </React.Fragment>
        ) : (
            <React.Fragment>
              <Typography>Waiting for data ...</Typography>
              <CircularProgress />
            </React.Fragment>
        )}
      </Box>
  );
}

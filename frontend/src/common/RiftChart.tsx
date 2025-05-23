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
import {CircularProgress, Grid2, Typography} from "@mui/material";
import {Echart} from "./Echart.tsx";
import {Serie} from "../utils/serie.tsx";
import {v4 as uuidv4} from "uuid";
import dayjs from "dayjs";

// Element are not required
export interface ChartOptions {
  series: Object[],
  xAxis: Object,
  yAxis: Object,
  grid: Object,
  dataZoom: Object[],
  tooltip: Object
}

export const RiftChart = (props: {
  series: Serie[],
  type: string,
}) => {
  const chartId = uuidv4();
  const maxLength = Math.max(...props.series.map(serie => serie.seriePoints.length));
  const categories = Array.from({ length: maxLength }, (_, i) => i + 1);
  const renderOptions = () => {
    const opt: ChartOptions = {
      xAxis: {
        type: 'category',
        data: categories,
        axisLabel: {
          show: false,
        },
      },
      yAxis: {
        nameLocation: 'end',
        type: 'value',
        show: true,
        axisLabel: {
          formatter: function (value: number) {
            return value + ' ' + props.series[0].unit;
          },
        },
      },
      grid: {
        left: '5%',
        right: '5%',
        bottom: '5%',
        top: '15%',
        containLabel: true
      },
      dataZoom: [
        {
          type: 'inside',
          realtime: true,
        }
      ],
      tooltip: {
        trigger: "axis",
        axisPointer: {
          type: "none",
          label: {
            backgroundColor: props.series[0].color,
          },
        },
        formatter: (params) => {
          return params.map(param => {
            const serie = props.series.find(s => s.name === param.seriesName);
            const originalDate = dayjs(serie?.seriePoints[param.dataIndex]?.date).format('DD MMM YYYY HH:mm');
            const value = param.data[1]?.toFixed(1);
            return `
              <div>
                <span style="display:inline-block;width:10px;height:10px;background-color:${serie?.color};margin-right:5px;"></span>
                <strong>${param.seriesName}</strong><br/>
                Date: ${originalDate}<br/>
                Value: ${value} ${serie?.unit}
              </div>
            `;
          }).join('<br/>');
        },
      },
      series: props.series.map((serie) => ({
        id: uuidv4(),
        name: serie.name,
        type: props.type,
        smooth: 0.2,
        symbol: 'diamond',
        itemStyle: {
          color: () => {
            return serie.color
          }
        },
        lineStyle: {
          color: serie.color,
          width: 1,
          shadowColor: serie.color,  // Shadow color
          shadowBlur: 3,        // Shadow blur size
          shadowOffsetX: 1,      // Shadow X offset
          shadowOffsetY: 1
        },
        data: serie.seriePoints.map((item, i) => [
          i,
          item.value,
        ]),
        animation: true,
        animationDuration: 1000,
      }))
    }
    return opt;
  }

  return (
    <Grid2 height={"100%"} mb={5}>
      <Box height={"100%"}>
        {props.series.length > 0 ? (
          <React.Fragment>
            <Box height={"100%"}
              width={"100%"}>
              <Echart id={chartId} options={renderOptions()}></Echart>
            </Box>
          </React.Fragment>
        ) : (
          <React.Fragment>
            <Typography>Waiting for data ...</Typography>
            <CircularProgress />
          </React.Fragment>
        )}
      </Box>
    </Grid2>
  );
}


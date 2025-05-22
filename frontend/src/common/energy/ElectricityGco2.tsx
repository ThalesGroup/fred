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

import ReactECharts from 'echarts-for-react';
import React from "react";
import {Paper, useTheme} from "@mui/material";
import dayjs from "dayjs";

interface Detail {
    name: string;
    kind: string;
    values: number[];
}

interface ElectricityMixChartProps {
    timestamps: string[];
    details: Detail[];
    precision: 'hourly' | 'daily';
    height?: string;  // Optional height prop, defaults if not provided
    width?: string;   // Optional width prop, defaults if not provided
}

export const ElectricityGco2: React.FC<ElectricityMixChartProps> = (
    {
        timestamps,
        details,
        precision,
        height = '400px',
        width = '100%'
}) => {
    const theme = useTheme();  // Access the theme

    // Helper function to format timestamps based on precision
    const formatTimestamp = (timestamp: string) => {
        return precision === 'hourly'
            ? new Date(timestamp).toLocaleTimeString()
            : new Date(timestamp).toLocaleDateString();
    };
    // console.log("MIX CHART", timestamps, details)
    // Ensure data is available before rendering the chart
    if (!timestamps || timestamps.length === 0 || !details || details.length === 0) {
        return null; // Render nothing if data is undefined or empty
    }

    // Format timestamps for x-axis
    const formattedTimestamps = timestamps.map(formatTimestamp);

    // Extract values for Renewable, Low Carbon, and calculate Fossil Fuels
    const directIntensity = details.find(detail => detail.name === 'Carbon Intensity gCO₂eq/kWh (direct)');
    const directIntensityValues = directIntensity ? directIntensity.values : [];
    const lcaIntensity = details.find(detail => detail.name === 'Carbon Intensity gCO₂eq/kWh (LCA)');
    const lcaIntensityValues = lcaIntensity ? lcaIntensity.values : [];

    // Define the chart options
    const option = {
        tooltip: {
            trigger: 'axis',
            axisPointer: {
                type: 'shadow',
            },
            formatter: function (params) {
                const dataIndex = params[0].dataIndex;
                const originalDate = dayjs(timestamps[dataIndex]).format('DD MMM YYYY HH:mm');

                // `params` contains the data for the series
                let tooltipContent = `Date: ${originalDate}<br/>`;  // Add the timestamp or category name
                params.forEach((item) => {
                    // Add each series value with rounding
                    const value = item.value.toFixed(1);  // Round to 1 decimal places
                    tooltipContent += `${item.marker} ${item.seriesName}: ${value}<br/>`;
                });
                return tooltipContent;
            },
        },
        legend: {
            data: ['Carbon Intensity gCO₂eq/kWh (direct)', 'Carbon Intensity gCO₂eq/kWh (LCA)'],
            orient: 'horizontal',  // Make the legend horizontal
            top: '0%',  // Position the legend at the bottom
            textStyle: {
                color: theme.palette.text.primary,  // Use text.primary from the theme
            },
        },
        grid: {
            left: '5%',
            right: '5%',
            bottom: '5%',
            top: '15%',
            containLabel: true,
        },
        dataZoom: [
            {
                type: 'inside',
                realtime: true,
            }
        ],
        xAxis: {
            type: 'category',
            data: formattedTimestamps, // Use formatted timestamps
            show: false
        },
        yAxis: {
            type: 'value',
            name: 'gCO₂eq/kWh',
            max: 100,
        },
        series: [
            {
                name: 'Carbon Intensity gCO₂eq/kWh (direct)',
                type: 'line',
                symbol: 'diamond',
                smooth: true,  // Make the line curved
                areaStyle: {
                    opacity: 0.1,
                },  // Fill the area under the line
                data: directIntensityValues,
                barCategoryGap: '0%',  // Remove gaps between bars
                barGap: '0%',  // Remove gaps between stacks
                itemStyle: {
                    color: theme.palette.chart.highBlue,
                },
            },
            {
                name: 'Carbon Intensity gCO₂eq/kWh (LCA)',
                type: 'line',
                symbol: 'diamond',
                smooth: true,  // Make the line curved
                areaStyle: {
                    opacity: 0.1,
                },  // Fill the area under the line
                data: lcaIntensityValues,
                barCategoryGap: '0%',  // Remove gaps between bars
                barGap: '0%',  // Remove gaps between stacks
                itemStyle: {
                    color: theme.palette.chart.lowBlue,
                },
            },
        ],
    };

    return (
        <Paper sx={{width: "100%"}}>
        <ReactECharts option={option} style={{ height: height, width: width }} />
        </Paper>
    )
};

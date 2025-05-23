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

export const ElectricityMixChart: React.FC<ElectricityMixChartProps> = (
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
    const renewableDetail = details.find(detail => detail.name === 'Renewable Percentage');
    const lowCarbonDetail = details.find(detail => detail.name === 'Low Carbon Percentage');

    const renewableValues = renewableDetail ? renewableDetail.values : [];
    const lowCarbonValues = lowCarbonDetail ? lowCarbonDetail.values : [];

    // Calculate the Non-Renewable Low Carbon part
    const nonRenewableLowCarbonValues = lowCarbonValues.map((lowCarbon, index) => {
        const renewable = renewableValues[index] || 0;
        return Math.max(lowCarbon - renewable, 0); // Ensure no negative values
    });

    // Fossil Fuels is calculated as the remainder after subtracting Low Carbon from 100%
    const fossilFuelsValues = lowCarbonValues.map((lowCarbon) => {
        return Math.max(100 - lowCarbon, 0); // Ensure no negative values
    });

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
                    tooltipContent += `${item.marker} ${item.seriesName}: ${value} %<br/>`;
                });
                return tooltipContent;
            },
        },
        legend: {
            data: ['Renewable', 'Non-Renewable Low Carbon', 'Fossil Fuels'],
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
        },
        yAxis: {
            type: 'value',
            name: '%',
            max: 100,
        },
        series: [
            {
                name: 'Renewable',
                type: 'line',
                symbol: 'diamond',
                smooth: true,  // Make the line curved
                areaStyle: {
                    opacity: 0.1,
                },  // Fill the area under the line
                stack: 'energy',
                data: renewableValues,
                barCategoryGap: '0%',  // Remove gaps between bars
                barGap: '0%',  // Remove gaps between stacks
                itemStyle: {
                    color: theme.palette.chart.lowBlue,
                },
            },
            {
                name: 'Non-Renewable Low Carbon',
                type: 'line',
                symbol: 'diamond',
                smooth: true,  // Make the line curved
                areaStyle: {
                    opacity: 0.1,
                },  // Fill the area under the line
                stack: 'energy',
                data: nonRenewableLowCarbonValues, // The part of Low Carbon that is not Renewable
                barCategoryGap: '0%',  // Remove gaps between bars
                barGap: '0%',  // Remove gaps between stacks
                itemStyle: {
                    color: theme.palette.chart.mediumBlue,
                },
            },
            {
                name: 'Fossil Fuels',
                type: 'line',
                symbol: 'diamond',
                smooth: true,  // Make the line curved
                areaStyle: {
                    opacity: 0.1,
                },  // Fill the area under the line
                stack: 'energy',
                data: fossilFuelsValues, // Calculated from the difference
                barCategoryGap: '0%',  // Remove gaps between bars
                barGap: '0%',  // Remove gaps between stacks
                itemStyle: {
                    color: theme.palette.chart.veryHighBlue,
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

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

import { useRef, useEffect, useState } from "react";
import ReactECharts from "echarts-for-react";
import { FactBadge } from "./FactBadge"; // Your FactBadge component
import { Box, useTheme } from "@mui/material";
import { Fact } from "../slices/factsStructures";
import FactsTable from "./FactsTable";

const FactsHexagonChart = ({ clusterDescription }) => {
  const theme = useTheme();
  const chartRef = useRef(null); // Reference to the ECharts instance
  const [positions, setPositions] = useState([]); // To store badge positions
  const [selectedFact, setSelectedFact] = useState<Fact | null>(null); // Track selected fact

  const generateHexagonData = () => {
    const hexData = [];
    const clusterRadius = 50;
    const namespaceRadius = 150;
    const workloadRadius = 250;

    clusterDescription.facts.forEach((fact, index) => {
      const angle = (index / clusterDescription.facts.length) * 2 * Math.PI;
      const x = Math.cos(angle) * clusterRadius;
      const y = Math.sin(angle) * clusterRadius;
      hexData.push({ x, y, fact });
    });

    clusterDescription.namespaces.forEach((namespace, nsIndex) => {
      namespace.facts.forEach((fact, factIndex) => {
        const angle =
          ((nsIndex + factIndex / namespace.facts.length) / clusterDescription.namespaces.length) * 2 * Math.PI;
        const x = Math.cos(angle) * namespaceRadius;
        const y = Math.sin(angle) * namespaceRadius;
        hexData.push({ x, y, fact });
      });

      namespace.workloads.forEach((workload, wlIndex) => {
        workload.facts.forEach((fact, factIndex) => {
          const angle =
            ((nsIndex + (wlIndex + factIndex / workload.facts.length) / namespace.workloads.length) /
              clusterDescription.namespaces.length) *
            2 *
            Math.PI;
          const x = Math.cos(angle) * workloadRadius;
          const y = Math.sin(angle) * workloadRadius;
          hexData.push({ x, y, fact });
        });
      });
    });

    return hexData;
  };

  const hexData = generateHexagonData();

  const option = {
    tooltip: {
      show: false, // Disable ECharts tooltip to avoid conflicts
    },
    xAxis: {
      type: "value",
      min: -300,
      max: 300,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { show: false },
      splitLine: { show: false },
    },
    yAxis: {
      type: "value",
      min: -200,
      max: 200,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { show: false },
      splitLine: { show: false },
    },
    series: [
      {
        type: "scatter", // Use scatter to define positions for badges
        data: hexData.map((item) => [item.x, item.y]), // Plot points
        coordinateSystem: "cartesian2d",
      },
      {
        type: "line",
        coordinateSystem: "cartesian2d",
        data: Array.from({ length: 360 }, (_, i) => {
          const angle = (i / 360) * 2 * Math.PI;
          return [Math.cos(angle) * 100, Math.sin(angle) * 100]; // First circle
        }),
        lineStyle: {
          type: "solid",
          width: 1,
          color: theme.palette.chart.highBlue,
        },
        showSymbol: false,
      },
      {
        type: "line",
        coordinateSystem: "cartesian2d",
        data: Array.from({ length: 360 }, (_, i) => {
          const angle = (i / 360) * 2 * Math.PI;
          return [Math.cos(angle) * 200, Math.sin(angle) * 200]; // Second circle
        }),
        lineStyle: {
          type: "solid",
          width: 1,
          color: theme.palette.chart.highGreen,
        },
        showSymbol: false,
      },
    ],
  };

  useEffect(() => {
    if (!chartRef.current) return;

    const instance = chartRef.current.getEchartsInstance();
    const updatePositions = () => {
      const newPositions = hexData.map((item) => {
        return {
          position: instance.convertToPixel({ seriesIndex: 0 }, [item.x, item.y]),
          fact: item.fact,
        };
      });
      setPositions(newPositions);
    };

    // Update badge positions when chart is rendered or resized
    instance.on("finished", updatePositions);
    window.addEventListener("resize", updatePositions);

    return () => {
      instance.off("finished", updatePositions);
      window.removeEventListener("resize", updatePositions);
    };
  }, [hexData]);

  return (
    <Box sx={{ height: "100%", width: "100%" }}>
      <Box sx={{ flexGrow: 1, position: "relative", height: "60%" }}>
        <ReactECharts ref={chartRef} option={option} style={{ height: "100%" }} />
        {positions.map(({ position, fact }, index) => (
          <div
            key={index}
            style={{
              position: "absolute",
              left: position[0] - 20, // Center the badge horizontally
              top: position[1] - 20, // Center the badge vertically
              pointerEvents: "auto", // Ensure pointer events are enabled
              zIndex: 10, // Ensure the badge is above the chart
              cursor: "pointer", // Change cursor on hover
            }}
            onClick={() => setSelectedFact(fact)}
          >
            <FactBadge fact={fact} size={40} />
          </div>
        ))}
      </Box>
      <Box p={4}>
        <FactsTable
          hexData={hexData} // Pass all hexData to the table
          selectedFact={selectedFact} // Pass the currently selected fact
          setSelectedFact={setSelectedFact} // Allow the table to update the selection
        />
      </Box>
    </Box>
  );
};

export default FactsHexagonChart;

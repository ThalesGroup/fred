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

import * as echarts from "echarts";
import { useEffect } from "react";
import type { EChartsOption } from "echarts";

export const Echart = (props: { id: string; options: Object }) => {
  useEffect(() => {
    const chartContainer = document.getElementById(props.id);
    if (chartContainer === null) return;

    let chart: echarts.ECharts;
    // init chart if it doesn't exist
    if (chartContainer.children.length === 0) {
      chart = echarts.init(chartContainer, "", {
        renderer: "canvas",
      });
    } else {
      chart = echarts.getInstanceByDom(chartContainer) as echarts.ECharts;
    }
    chart.setOption(props.options as EChartsOption, true, true);
    window.addEventListener("resize", () => chart.resize());
  }, [props.id, props.options]);
  return <div id={props.id} style={{ width: "100%", height: "100%" }}></div>;
};

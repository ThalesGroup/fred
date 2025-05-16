import * as echarts from 'echarts';
import {useEffect} from "react";
import type { EChartsOption } from 'echarts';


export const Echart = (
  props: {
    id: string,
    options: Object
  }) => {
  useEffect(() => {
    const chartContainer = document.getElementById(props.id);
    if (chartContainer === null) return;

    let chart: echarts.ECharts;
    // init chart if it doesn't exist
    if (chartContainer.children.length === 0) {
      chart = echarts.init(chartContainer, '', {
        renderer: 'canvas',
      });
    } else {
      chart = echarts.getInstanceByDom(chartContainer) as echarts.ECharts;
    }
    chart.setOption(props.options as EChartsOption, true, true);
    window.addEventListener('resize', () => chart.resize());
  }, [props.id, props.options]);
  return (
    <div  id={props.id} style={{width: '100%', height: '100%'}}></div>
  );
}

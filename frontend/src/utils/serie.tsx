import {ClusterConsumption} from "../frugalit/slices/api.tsx";

export interface SeriePoint {
  date: string;
  value: number;
}

// Serie interface used for bar and line charts
export interface Serie {
  name: string;
  color: string;
  unit: string;
  seriePoints: SeriePoint[];
}

// Returns the mean value of serie in the given array
export const getMeanValue = (serie: Serie): number => {
  if (!serie.seriePoints) return 0;
  return Math.round(serie.seriePoints.reduce((sum, { value }) => sum + value, 0) / serie.seriePoints.length);
};

// Returns the maximum value of serie in the given array
export const getMaxValue = (series: Serie[]): number => {
  if (!Array.isArray(series)) return 0;
  return series.reduce((globalMax, serie) => {
    if (!serie.seriePoints || serie.seriePoints.length === 0) return globalMax;
    const serieMax = serie.seriePoints.reduce((max, { value }) => Math.max(max, value), serie.seriePoints[0].value);
    return Math.max(globalMax, serieMax);
  }, 0);
};

// Returns the minimum value of serie in the given array
export const getMinValue = (serie: Serie): number => {
  if (!serie.seriePoints) return 0;
  return serie.seriePoints.reduce((max, { value }) => Math.min(max, value), serie.seriePoints[0] ? serie.seriePoints[0].value : 0)
};

// Returns the sum of values in the given array
export const getSumValue = (serie: Serie): number => {
  if (!serie.seriePoints) return 0;
  return parseFloat(serie.seriePoints.reduce((sum, { value }) => sum + value, 0).toFixed(0));
};

// Returns a Serie Object from a ClusterConsumption Object
export const transformClusterConsumptionToSerie = (
  clusterConsumptionArray: ClusterConsumption,
  name: string,
  color: string,
): Serie => {
  return {
    name: name,
    color: color,
    unit: clusterConsumptionArray.unit,
    seriePoints: clusterConsumptionArray.values.map((value, index) => ({
      date: clusterConsumptionArray.timestamps[index],
      value: Math.round(value * 100) / 100,
    }))
  };
};
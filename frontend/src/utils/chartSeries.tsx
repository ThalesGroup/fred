import { Serie } from "./serie";

export interface ChartSeries {
    name: string,
    color: string,
    unit: string,
    serieTypes: SerieType[]
}

export interface SerieType {
    logos: string[],
    color: string,
    series: Serie[]
}
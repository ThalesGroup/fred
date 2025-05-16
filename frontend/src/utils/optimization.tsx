export interface ClusterConsumption {
  timestamps: string [];
  values: number [];
  auc: number;
  unit: string;
  details?: Detail[]
}

export interface Detail {
  name: string;
  kind: string;
  timestamps: string[];
  values: number[];
}
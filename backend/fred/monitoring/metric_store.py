# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
metric_store.py

This module defines the `MetricStore` class for in-memory storage, filtering, and persistence
of structured metric logs.

Key features:
- Store and retrieve metrics in-memory (list of dictionaries)
- Append or overwrite metrics to disk using JSON Lines format
- Load metrics back into memory from file
- Filter metrics by date range and resample by time precision
- Export results as a pandas DataFrame or a list of dictionaries

Typical use case:
    store = MetricStore()
    store.add_metric({...})
    store.save_to_file("logs.jsonl")
    metrics_df = store.get_by_date_range(start, end, precision="minute")

This class is especially useful for lightweight monitoring, logging, and analytics.
"""

import json
from typing import List, Dict, Any, Optional, Union
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np


class MetricStore:
    """
    In-memory metric store with JSONL export/import and filtering by date with time precision.
    """

    def __init__(self):
        self._metrics: List[Dict[str, Any]] = []

    def __len__(self) -> int:
        return len(self._metrics)

    def add_metric(self, metric: Dict[str, Any]) -> None:
        """
        Add a single metric to the in-memory store.

        Args:
            metric (dict): A dictionary containing metric data, typically with a 'timestamp' key.
        """
        self._metrics.append(metric)

    def get_all(self) -> List[Dict[str, Any]]:
        """
        Return all metrics currently in memory.

        Returns:
            List[Dict[str, Any]]: The list of stored metric dictionaries.
        """
        return self._metrics

    def clear(self) -> None:
        """
        Clear all stored metrics from memory.
        """
        self._metrics.clear()

    def save_to_file(self, filepath: Union[str,Path], append: bool = True) -> None:
        """
        Persist metrics to a file in JSON Lines format.

        Args:
            filepath (str): Destination file path.
            append (bool): If True, append to the file; otherwise overwrite.
        """
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"

        with open(path, mode, encoding="utf-8") as f:
            for metric in self._metrics:
                json.dump(metric, f)
                f.write("\n")

    def load_from_file(self, filepath: str) -> None:
        """
        Load metrics from a JSON Lines file into memory.

        Args:
            filepath (str): Path to the JSONL file.
        
        Raises:
            FileNotFoundError: If the file does not exist.
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"{filepath} not found.")

        with open(path, "r", encoding="utf-8") as f:
            self._metrics = [json.loads(line) for line in f if line.strip()]

    def get_all_by_date_range(self, start: datetime, end: datetime) -> List[Dict[str, Any]]:
        return [
            m for m in self._metrics
            if start.timestamp() <= m.get("timestamp", 0) <= end.timestamp()
        ]
    
    def _get_filtered_df(self, start: datetime, end: datetime) -> pd.DataFrame:
        df = pd.json_normalize(self._metrics)
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", errors="coerce")
        df = df.dropna(subset=["timestamp"])
        return df[(df["timestamp"] >= start) & (df["timestamp"] <= end)]


    def get_numerical_by_date_range(
        self, start: datetime, end: datetime, precision: str = "minute"
    ) -> List[Dict[str, Any]]:

        freq_map = {"second": "S", "minute": "T", "hour": "H", "day": "D"}
        if precision not in freq_map:
            raise ValueError("Invalid precision. Choose from second, minute, hour, day.")

        df = pd.json_normalize(self._metrics)
        df = self._get_filtered_df(start, end)

        if df.empty:
            return []

        df.set_index("timestamp", inplace=True)
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        df_agg = df[numeric_cols].resample(freq_map[precision]).mean(numeric_only=True).reset_index()
        df_agg = df_agg.replace({np.nan: None, np.inf: None, -np.inf: None})
        return df_agg.to_dict(orient="records")


    def get_categorical_by_date_range(self, start: datetime, end: datetime) -> List[Dict[str, Any]]:
        import pandas as pd

        df = pd.json_normalize(self._metrics)
        df = self._get_filtered_df(start, end)

        if df.empty:
            return []

        cat_cols = [
            "user_id", "model_type", "model_name", "finish_reason", "session_id"
        ]

        result = []
        for _, group in df.groupby(pd.Grouper(key="timestamp", freq="T")):
            if group.empty:
                continue
            data = {"timestamp": group["timestamp"].iloc[0]}
            for col in cat_cols:
                if col in group.columns:
                    data[col] = list(group[col].dropna().unique())
            result.append(data)
        return result
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


class MetricStore:
    """
    In-memory metric store with JSONL export/import and filtering by date with time precision.
    """

    def __init__(self):
        self._metrics: List[Dict[str, Any]] = []

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

    def save_to_file(self, filepath: str, append: bool = True) -> None:
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

    def get_by_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        precision: str = "second",
        as_dict: bool = False
    ) -> Union[pd.DataFrame, List[Dict[str, Any]]]:
        """
        Filter and group metrics between two datetimes with a given time precision.

        Args:
            start_date (datetime): Start of the date range (inclusive).
            end_date (datetime): End of the date range (inclusive).
            precision (str): Aggregation granularity. One of 'second', 'minute', 'hour', 'day'.
            as_dict (bool): If True, return the result as a list of dictionaries instead of a DataFrame.

        Returns:
            Union[pd.DataFrame, List[Dict[str, Any]]]: Aggregated metrics.

        Raises:
            ValueError: If the precision is invalid or timestamp format is incorrect.
            KeyError: If 'timestamp' is missing from any metric.
        """
        freq_map = {
            "second": "S",
            "minute": "T",
            "hour": "H",
            "day": "D"
        }

        if precision not in freq_map:
            raise ValueError("Invalid precision. Use: 'second', 'minute', 'hour', 'day'.")

        if not self._metrics:
            return [] if as_dict else pd.DataFrame()

        df = pd.DataFrame(self._metrics)

        if "timestamp" not in df.columns:
            raise KeyError("Each metric must contain a 'timestamp' key.")

        try:
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", errors="raise")
        except Exception as e:
            raise ValueError(f"Invalid timestamp format: {e}")

        mask = (df["timestamp"] >= start_date) & (df["timestamp"] <= end_date)
        df_filtered = df.loc[mask]

        if df_filtered.empty:
            return [] if as_dict else pd.DataFrame()

        df_filtered.set_index("timestamp", inplace=True)
        df_grouped = df_filtered.resample(freq_map[precision]).mean(numeric_only=True)
        df_grouped = df_grouped.reset_index()

        return df_grouped.to_dict(orient="records") if as_dict else df_grouped

import logging
import os
from typing import Optional, List, Dict, Any

import pandas as pd
import datetime
import io
import contextlib
import numpy as np
from scipy import stats
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from RestrictedPython import compile_restricted
from RestrictedPython import safe_globals
from app.features.statistic.utils import safe_eval_function

logger = logging.getLogger(__name__)


class StatisticService:
    def __init__(
        self,
        csv_path: str = "/home/thomas/.fred/knowledge-flow/statistic/data/data.csv",
        graphiques_dir: str = "/home/thomas/.fred/knowledge-flow/statistic/data/graphiques",
    ):
        self.csv_path = csv_path
        self.graphiques_dir = graphiques_dir
        os.makedirs(self.graphiques_dir, exist_ok=True)
        self._load_data()

    def _load_data(self):
        try:
            self.df = pd.read_csv(self.csv_path)
            logger.info(f"✅ Data loaded from {self.csv_path} with shape {self.df.shape}")
        except Exception as e:
            logger.error(f"❌ Failed to load CSV file {self.csv_path}", exc_info=True)
            self.df = pd.DataFrame()

    def reload_data(self):
        self._load_data()

    def _save_data(self):
        try:
            self.df.to_csv(self.csv_path, index=False)
            self.reload_data()
            logger.info(f"💾 Data saved to {self.csv_path}")
        except Exception as e:
            logger.error(f"❌ Failed to save CSV to {self.csv_path}", exc_info=True)
            raise

    def describe_data(self, columns: Optional[List[str]] = None) -> Dict[str, Any]:
        try:
            df = self.df if columns is None else self.df[columns]

            head = df.head(5).replace({np.nan: None}).to_dict(orient='records')

            dtypes = {col: str(dtype) for col, dtype in df.dtypes.items()}
            null_counts = df.isnull().sum().to_dict()
            unique_counts = df.nunique(dropna=False).to_dict()

            description_raw = df.describe(include='all').replace({np.nan: None})
            if isinstance(description_raw, pd.Series):
                description_raw = description_raw.to_frame().T
            description_dict = description_raw.to_dict()

            skewness = df.skew(numeric_only=True).to_dict()
            kurtosis = df.kurt(numeric_only=True).to_dict()

            description = {}
            total_rows = df.shape[0]

            for col in df.columns:
                stats = description_dict.get(col, {})
                col_dict = {str(k): v for k, v in stats.items()}
                col_dict["dtype"] = dtypes.get(col, "unknown")
                col_dict["null_count"] = null_counts.get(col, 0)
                col_dict["null_percentage"] = round(100 * null_counts.get(col, 0) / total_rows, 2) if total_rows > 0 else None
                col_dict["unique_count"] = unique_counts.get(col, 0)
                col_dict["unique_percentage"] = round(100 * unique_counts.get(col, 0) / total_rows, 2) if total_rows > 0 else None

                if col in skewness and not pd.isna(skewness[col]):
                    col_dict["skewness"] = skewness[col]
                if col in kurtosis and not pd.isna(kurtosis[col]):
                    col_dict["kurtosis"] = kurtosis[col]

                col_dict = {k: v for k, v in col_dict.items() if v not in [np.nan, "null", None, "NaN"]}

                description[col] = col_dict

            shape = {"rows": total_rows, "columns": df.shape[1]}

            logger.info(f"📊 Data description generated (columns={columns})")

            return {
                "head": head,
                "description": description,
                "shape": shape
            }

        except Exception as e:
            logger.error(f"❌ Failed to describe data (columns={columns})", exc_info=True)
            raise

    def delete_column(self, column_name: str) -> None:
        """
        Delete a column from the DataFrame.
        """
        try:
            if column_name not in self.df.columns:
                raise ValueError(f"Column '{column_name}' does not exist.")
            self.df.drop(columns=[column_name], inplace=True)
            self._save_data()
            logger.info(f"🗑️ Column '{column_name}' deleted.")
        except Exception as e:
            logger.error(f"❌ Failed to delete column '{column_name}'", exc_info=True)
            raise

    def update_column(self, column_name: str, func_str: str) -> None:
        """
        Apply a function (provided as a string) to a DataFrame column.
        Optionally allows the use of a dictionary named `mapping` within the function.
        """
        try:
            if column_name not in self.df.columns:
                raise ValueError(f"Column '{column_name}' does not exist.")

            func = safe_eval_function(func_str)

            self.df[column_name] = self.df[column_name].apply(func)
            self._save_data()
            logger.info(f"✅ Column '{column_name}' successfully updated.")

        except Exception as e:
            logger.error(f"❌ Failed to update column '{column_name}'", exc_info=True)

    def add_transformed_column(self, new_column_name: str, source_column_name: str, func_str: str) -> None:
        """
        Create a new column based on an existing column
        by applying a function provided as a string.
        """
        try:
            if source_column_name not in self.df.columns:
                raise ValueError(f"Source column '{source_column_name}' does not exist.")
            if new_column_name in self.df.columns:
                raise ValueError(f"Target column '{new_column_name}' already exists.")

            func = safe_eval_function(func_str)

            self.df[new_column_name] = self.df[source_column_name].apply(func)
            self._save_data()
            logger.info(f"✅ Column '{new_column_name}' created from '{source_column_name}' with transformation '{func_str}'.")

        except Exception as e:
            logger.error(f"❌ Failed to create column '{new_column_name}' from '{source_column_name}'", exc_info=True)
            raise

    def ab_test(self, group_col: str, metric_col: str, alpha=0.05) -> Dict[str, Any]:
        try:
            if group_col not in self.df.columns or metric_col not in self.df.columns:
                raise ValueError(f"Columns '{group_col}' or '{metric_col}' not found.")

            groups = self.df[group_col].unique()
            if len(groups) != 2:
                raise ValueError("A/B test requires exactly two groups.")

            group1 = self.df[self.df[group_col] == groups[0]][metric_col].dropna()
            group2 = self.df[self.df[group_col] == groups[1]][metric_col].dropna()

            t_stat, p_value = stats.ttest_ind(group1, group2, equal_var=False)
            significant = p_value < alpha

            result = {
                "group_1": groups[0],
                "group_2": groups[1],
                "t_statistic": t_stat,
                "p_value": p_value,
                "significant": significant,
                "alpha": alpha,
            }

            logger.info(f"🧪 A/B test performed on '{metric_col}' grouped by '{group_col}' | p={p_value:.4f}")
            return result
        except Exception as e:
            logger.error(f"❌ A/B test failed (group_col={group_col}, metric_col={metric_col})", exc_info=True)
            raise

    def plot_histogram(self, column: str, bins: int = 30) -> str:
        try:
            if column not in self.df.columns:
                raise ValueError(f"Column '{column}' not found.")

            plt.figure(figsize=(8, 6))
            sns.histplot(self.df[column].dropna(), bins=bins, kde=True)
            plt.title(f"Histogram of {column}")
            plt.xlabel(column)
            plt.ylabel("Frequency")

            save_path = os.path.join(self.graphiques_dir, f"histogram_{column}.png")
            plt.savefig(save_path)
            plt.close()

            logger.info(f"📈 Histogram for '{column}' saved to {save_path}")
            return save_path
        except Exception as e:
            logger.error(f"❌ Failed to plot histogram for column '{column}'", exc_info=True)
            raise

    def plot_scatter(self, x_col: str, y_col: str) -> str:
        try:
            if x_col not in self.df.columns or y_col not in self.df.columns:
                raise ValueError(f"Columns '{x_col}' or '{y_col}' not found.")

            plt.figure(figsize=(8, 6))
            sns.scatterplot(x=self.df[x_col], y=self.df[y_col])
            plt.title(f"Scatter plot of {y_col} vs {x_col}")
            plt.xlabel(x_col)
            plt.ylabel(y_col)

            save_path = os.path.join(self.graphiques_dir, f"scatter_{x_col}_vs_{y_col}.png")
            plt.savefig(save_path)
            plt.close()

            logger.info(f"📊 Scatter plot of '{y_col}' vs '{x_col}' saved to {save_path}")
            return save_path
        except Exception as e:
            logger.error(f"❌ Failed to plot scatter ({x_col} vs {y_col})", exc_info=True)
            raise

    def train_model(
        self,
        target_column: str,
        feature_columns: List[str],
        model_type: str = "linear_regression",
        model_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        try:
            if target_column not in self.df.columns:
                raise ValueError(f"Target column '{target_column}' not found.")
            for col in feature_columns:
                if col not in self.df.columns:
                    raise ValueError(f"Feature column '{col}' not found.")

            X = self.df[feature_columns].select_dtypes(include=[np.number]).dropna()
            y = self.df.loc[X.index, target_column]
            model_params = model_params or {}

            if model_type == "linear_regression":
                model = LinearRegression(**model_params)
                model.fit(X, y)
                score = model.score(X, y)
                coefs = dict(zip(feature_columns, model.coef_))
                result = {"model": "Linear Regression", "score_r2": score, "coefficients": coefs}

            elif model_type == "random_forest":
                model = RandomForestRegressor(**model_params)
                model.fit(X, y)
                score = model.score(X, y)
                importances = dict(zip(feature_columns, model.feature_importances_))
                result = {"model": "Random Forest", "score_r2": score, "feature_importances": importances}

            else:
                raise ValueError(f"Unsupported model type: {model_type}")

            logger.info(f"🤖 Model '{model_type}' trained on target '{target_column}' with score {score:.4f}")
            return result
        except Exception as e:
            logger.error(f"❌ Model training failed (type={model_type}, target={target_column})", exc_info=True)
            raise
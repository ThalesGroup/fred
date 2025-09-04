import os
import base64
import logging
import joblib
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

from typing import List, Dict, Any
from scipy import stats
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import confusion_matrix, accuracy_score, r2_score, mean_absolute_error, root_mean_squared_error

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class StatisticService:
    def __init__(self, graphiques_dir: str = "/home/thomas/.fred/knowledge-flow/statistic/data/graphiques", models_dir: str = "/home/thomas/.fred/knowledge-flow/statistic/data/models"):
        self.df = None
        self.graphiques_dir = graphiques_dir
        self.models_dir = models_dir
        os.makedirs(graphiques_dir, exist_ok=True)
        os.makedirs(models_dir, exist_ok=True)

    def set_dataset(self, df: pd.DataFrame):
        self.df = df

    def is_loaded(self) -> bool:
        return self.df is not None and not self.df.empty

    def check_df_loaded(self):
        if not self.is_loaded():
            raise ValueError("❌ No dataset loaded. Use 'set_dataset()' to load a DataFrame.")

    def check_model_loaded(self):
        if not hasattr(self, "current_model"):
            raise ValueError("❌ No model is trained or loaded. Use 'train_model()' or 'load_model()'.")

    def head(self, n: int = 5):
        if self.df is None:
            raise ValueError("No dataset loaded, check which datasets are available and set one.")
        return self.df.head(n).to_dict(orient="records")

    def describe_data(self) -> Dict[str, Any]:
        if self.df is None:
            raise ValueError("No dataset loaded, check which datasets are available and set one.")
        df = self.df
        desc = df.describe(include="all").to_dict()
        top_values = {col: df[col].value_counts(dropna=False).head(3).to_dict() for col in df.columns}
        correlations = df.corr(numeric_only=True).to_dict()

        outliers = {}
        for col in df.select_dtypes(include=[np.number]).columns:
            series = df[col].dropna()
            z_score: np.ndarray = stats.zscore(series)
            z = np.abs(z_score)
            outliers[col] = int((z > 3).sum())

        return {"description": desc, "top_values": top_values, "correlations": correlations, "outliers": outliers, "shape": {"rows": df.shape[0], "columns": df.shape[1]}}

    def detect_outliers(self, method="zscore", threshold=3.0) -> Dict[str, List[int]]:
        if self.df is None:
            raise ValueError("No dataset loaded, check which datasets are available and set one.")
        df = self.df
        outliers = {}
        for col in df.select_dtypes(include=[np.number]).columns:
            series = df[col].dropna()
            if method == "zscore":
                z = np.abs(stats.zscore(series))
                idxs = series.index[z > threshold]
                if hasattr(idxs, "tolist"):
                    outliers[col] = idxs.tolist()
                else:
                    outliers[col] = list(idxs) if isinstance(idxs, (tuple, list)) else [idxs]
            elif method == "iqr":
                Q1 = series.quantile(0.25)
                Q3 = series.quantile(0.75)
                IQR = Q3 - Q1
                mask = (series < Q1 - threshold * IQR) | (series > Q3 + threshold * IQR)
                idxs = series.index[mask]
                if hasattr(idxs, "tolist"):
                    outliers[col] = idxs.tolist()
                else:
                    outliers[col] = list(idxs) if isinstance(idxs, (tuple, list)) else [idxs]
        return outliers

    def correlation_analysis(self, top_n: int = 5) -> List[Dict[str, Any]]:
        if self.df is None:
            raise ValueError("No dataset loaded, check which datasets are available and set one.")
        corr_matrix = self.df.corr(numeric_only=True)
        corr_pairs = corr_matrix.unstack().reset_index()
        corr_pairs.columns = ["var1", "var2", "correlation"]
        corr_pairs = corr_pairs[corr_pairs["var1"] != corr_pairs["var2"]]
        top_corr = corr_pairs.reindex(corr_pairs["correlation"].abs().sort_values(ascending=False).index).drop_duplicates().head(top_n)
        return top_corr.to_dict(orient="records")

    def plot_histogram(self, column: str, bins: int = 30, to_base64: bool = False) -> str:
        if self.df is None:
            raise ValueError("No dataset loaded, check which datasets are available and set one.")
        if column not in self.df.columns:
            raise ValueError(f"❌ Column '{column}' not found in dataset.")
        plt.figure(figsize=(8, 6))
        sns.histplot(self.df[column].dropna(), bins=bins, kde=True)
        plt.title(f"Histogram of {column}")
        plt.tight_layout()
        path = os.path.join(self.graphiques_dir, f"hist_{column}.png")
        plt.savefig(path)
        plt.close()
        if to_base64:
            with open(path, "rb") as img:
                return base64.b64encode(img.read()).decode()
        return path

    def plot_scatter(self, x_col: str, y_col: str, to_base64=False) -> str:
        if self.df is None:
            raise ValueError("No dataset loaded, check which datasets are available and set one.")
        if x_col not in self.df.columns or y_col not in self.df.columns:
            raise ValueError(f"❌ One or both columns '{x_col}', '{y_col}' not found in dataset.")
        plt.figure(figsize=(8, 6))
        sns.scatterplot(data=self.df, x=x_col, y=y_col)
        plt.title(f"{y_col} vs {x_col}")
        plt.tight_layout()
        path = os.path.join(self.graphiques_dir, f"scatter_{x_col}_vs_{y_col}.png")
        plt.savefig(path)
        plt.close()
        if to_base64:
            with open(path, "rb") as img:
                return base64.b64encode(img.read()).decode()
        return path

    def train_model(self, target: str, features: List[str], model_type: str) -> Dict[str, Any]:
        if self.df is None:
            raise ValueError("No dataset loaded, check which datasets are available and set one.")
        df = self.df.dropna(subset=[target] + features)
        if df.empty:
            raise ValueError("❌ No data available after dropping NaNs in features/target.")

        X = pd.get_dummies(df[features], drop_first=True)
        y = df[target]

        self.feature_columns = X.columns.tolist()
        is_classification = y.dtype == "object" or y.dtype.name == "category" or y.nunique() < 20
        self.is_classification = is_classification

        if is_classification:
            self.label_encoder = LabelEncoder()
            y = self.label_encoder.fit_transform(y)
            if model_type == "linear":
                model = LogisticRegression()
            elif model_type == "random_forest":
                model = RandomForestClassifier()
            else:
                raise ValueError("❌ Unknown model type")
        else:
            if model_type == "linear":
                model = LinearRegression()
            elif model_type == "random_forest":
                model = RandomForestRegressor()
            else:
                raise ValueError("❌ Unknown model type")

        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        model.fit(X_train, y_train)

        self.current_model = model
        self.X_test = X_test
        self.y_test = y_test
        self.y_pred = model.predict(X_test)

        metrics = {}
        if self.is_classification:
            metrics["accuracy"] = accuracy_score(y_test, self.y_pred)
            metrics["confusion_matrix"] = confusion_matrix(y_test, self.y_pred).tolist()
        else:
            metrics["r2"] = r2_score(y_test, self.y_pred)
            metrics["rmse"] = root_mean_squared_error(y_test, self.y_pred)
            metrics["mae"] = mean_absolute_error(y_test, self.y_pred)

        logger.info(f"✅ Model '{model_type}' trained | Metrics: {metrics}")
        return {"model_type": model_type, "metrics": metrics}

    def evaluate_model(self) -> Dict[str, Any]:
        self.check_model_loaded()
        if not hasattr(self, "y_test") or not hasattr(self, "y_pred"):
            raise ValueError("❌ No evaluation data found. Train a model first.")
        metrics = {}
        if self.is_classification:
            metrics["accuracy"] = accuracy_score(self.y_test, self.y_pred)
            metrics["confusion_matrix"] = confusion_matrix(self.y_test, self.y_pred).tolist()
        else:
            metrics["r2"] = r2_score(self.y_test, self.y_pred)
            metrics["rmse"] = root_mean_squared_error(self.y_test, self.y_pred)
            metrics["mae"] = mean_absolute_error(self.y_test, self.y_pred)
        return metrics

    def predict_from_row(self, row: Dict[str, Any]) -> Any:
        self.check_model_loaded()
        df_row = pd.DataFrame([row])
        df_row = pd.get_dummies(df_row, drop_first=True)

        for col in self.feature_columns:
            if col not in df_row.columns:
                df_row[col] = 0
        df_row = df_row[self.feature_columns]
        prediction = self.current_model.predict(df_row)[0]
        if self.is_classification:
            return self.label_encoder.inverse_transform([prediction])[0]
        else:
            return prediction

    def save_model(self, name: str):
        self.check_model_loaded()
        path = os.path.join(self.models_dir, f"{name}.pkl")
        to_save = {"model": self.current_model, "feature_columns": self.feature_columns}
        joblib.dump(to_save, path)
        logger.info(f"💾 Model and features saved to {path}")

    def list_models(self) -> List[str]:
        return [f for f in os.listdir(self.models_dir) if f.endswith(".pkl")]

    def load_model(self, name: str):
        path = os.path.join(self.models_dir, f"{name}.pkl")
        if not os.path.exists(path):
            raise FileNotFoundError(f"❌ Model file '{name}.pkl' not found in '{self.models_dir}'.")
        try:
            data = joblib.load(path)
            self.current_model = data["model"]
            self.feature_columns = data["feature_columns"]
            logger.info(f"📦 Model and features loaded from {path}")
        except Exception as e:
            raise RuntimeError(f"❌ Failed to load model: {str(e)}")

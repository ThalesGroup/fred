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

from datetime import datetime, timedelta
from typing import Tuple, Dict, Optional
from fastapi import HTTPException
import logging
import traceback
import pandas as pd
import yaml
from functools import wraps
import inspect

logger = logging.getLogger(__name__)

from app.common.structures import Configuration, PrecisionEnum, SampleDataType, Series, CompareResult, Window, Difference
from app.common.error import SESSION_NOT_INITIALIZED

def parse_server_configuration(configuration_path: str) -> Configuration:
    """
    Parses the server configuration from a YAML file.

    Args:
        configuration_path (str): The path to the configuration YAML file.

    Returns:
        Configuration: The parsed configuration object.
    """
    with open(configuration_path, "r") as f:
        try:
            config: Dict = yaml.safe_load(f)
        except yaml.YAMLError as e:
            print(f"Error while parsing configuration file {configuration_path}: {e}")
            exit(1)
    return Configuration(**config)


def sample_data(
        x: list[datetime],
        y: list[float],
        precision: PrecisionEnum,
        data_type: SampleDataType
) -> Tuple[list[datetime], list[float]]:
    """
    Downsample the data to the given step
    """
    if not x or not y:
        return [], []
    df = pd.DataFrame({'x': x, 'y': y})
    df.set_index('x', inplace=True)
    df.index = pd.to_datetime(df.index)

    pandas_precision = precision.to_pandas_precision()
    if pandas_precision is None:
        resampled_data = df
    else:
        match data_type.value:
            case SampleDataType.AVERAGE:
                resampled_data = df.resample(pandas_precision, origin='start').mean()
                resampled_data = resampled_data.ffill()
            case SampleDataType.SUM:
                resampled_data = df.resample(pandas_precision, origin='start').sum()
            case _:
                raise NotImplementedError(f"Data type {data_type.value} not supported")

    resampled_data = resampled_data.round(2)
    return resampled_data.index.to_list(), resampled_data['y'].to_list()


def to_timedelta(duration_str: str) -> timedelta:
    """
    Parse a duration string into a timedelta object.

    Args:
        duration_str (str): A string representing a duration in the format "NdNhNmNs",
            where N is a number, d represents days, h represents hours,
            m represents minutes, and s represents seconds.

    Returns:
        timedelta: A timedelta object representing the parsed duration.

    Raises:
        ValueError: If the input duration string is not in the correct format or contains invalid characters.

    Example:
        >>> to_timedelta("2d3h30m15s")
        datetime.timedelta(days=2, seconds=12615)

    """
    days = 0
    hours = 0
    minutes = 0
    seconds = 0

    current_number = ''
    for ch in duration_str:
        if ch.isdigit():
            current_number += ch
        else:
            if ch == 'd':
                days = int(current_number)
            elif ch == 'h':
                hours = int(current_number)
            elif ch == 'm':
                minutes = int(current_number)
            elif ch == 's':
                seconds = int(current_number)
            else:
                raise ValueError('Invalid duration, valid format is format "NdNhNmNs", where N is a number, '
                                 'd represents days, h represents hours, m represents minutes, and s represents '
                                 'seconds')
            current_number = ''

    return timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)


def auc_calculation(values: list[float]) -> float:
    """
    Calculate the area under the curve of the consumption during the period
    """
    return sum(values)


def resample_series(series: Series,
                    precision: PrecisionEnum) -> Series:
    """
    Resample the series data to the given precision
    """
    resampled_timestamps, resampled_values = sample_data(
        series.timestamps,
        series.values,
        precision, SampleDataType.SUM
    )
    return Series(
        timestamps=resampled_timestamps,
        values=resampled_values,
        auc=auc_calculation(resampled_values),
        unit=series.unit
    )


# Used to explain the comparison in all the routes that propose a comparison between two windows
API_COMPARE_DOC = """
This endpoint compares the total metric values between two time windows.

The difference is computed as follows:
- **Difference Value**: This is calculated as the total value in the second window minus the total value in the first window.
For example, if the total in window 1 is 22 and in window 2 is 10, the difference value is `10 - 22 = -12`.
- **Difference Percentage**: This is calculated as the difference value divided by the total value of the first window, multiplied by 100 to get the percentage.
For example, if the total in window 1 is 22 and the difference value is -12, the percentage difference is `(-12 / 22) * 100 = -54.55%`.
"""


def compare_two_windows(window_1: Series, window_2: Series,
                        start_window_1: datetime, end_window_1: datetime,
                        start_window_2: datetime, end_window_2: datetime,
                        cluster: str) -> CompareResult:
    if window_1.unit != window_2.unit:
        raise ValueError(
            f"Got two different units, unable to compare '{window_1.unit}' and '{window_2.unit}'")
    diff_total = window_2.auc - window_1.auc
    percentage = (diff_total / window_1.auc) * 100
    return CompareResult(
        cluster=cluster,
        unit=window_1.unit,
        window_1=Window(start=start_window_1, end=end_window_1, total=window_1.auc),
        window_2=Window(start=start_window_2, end=end_window_2, total=window_2.auc),
        difference=Difference(value=diff_total, percentage=percentage),
    )
    
def format_to_en(number) -> float:
    return str(number).replace(",", ".")

import logging
import traceback
from typing import Optional

logger = logging.getLogger(__name__)

def log_exception(e: Exception, context_message: Optional[str] = None) -> str:
    """
    Logs an exception with full details (preserving caller's location)
    and returns a short, user-friendly summary string for UI display.

    Args:
        e (Exception): The exception to log.
        context_message (Optional[str]): Additional context for the logs.

    Returns:
        str: A human-readable summary of the exception.
    """
    error_type = type(e).__name__
    error_message = str(e)
    stack_trace = traceback.format_exc()

    # Detect root cause if chained exception
    cause = getattr(e, '__cause__', None) or getattr(e, '__context__', None)
    root_cause = repr(cause) if cause else error_message

    # Short, user-friendly summary
    user_hint = ""
    if "Connection refused" in error_message:
        user_hint = "A service might be down or unreachable."
    elif "timeout" in error_message.lower():
        user_hint = "The system took too long to respond."
    elif "not found" in error_message.lower():
        user_hint = "Something you're trying to access doesn't exist."
    elif "authentication" in error_message.lower():
        user_hint = "There might be a credentials or permissions issue."
    else:
        user_hint = "An unexpected error occurred."

    # ✅ Compose final summary string
    summary = f"{error_type}: {error_message} — {user_hint}"

    # Log full details
    logger.error("Exception occurred: %s", error_type, stacklevel=2)
    if context_message:
        logger.error("🔍 Context: %s", context_message, stacklevel=2)
    logger.error("🧩 Error message: %s", error_message, stacklevel=2)
    logger.error("📦 Root cause: %s", root_cause, stacklevel=2)
    logger.error("🧵 Stack trace:\n%s", stack_trace, stacklevel=2)

    return summary

# Decorator for wrapping methods to protect by authentication
def authorization_required(method):
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        sig = inspect.signature(method)
        bound_args = sig.bind(self, *args, **kwargs)
        bound_args.apply_defaults()

        arguments = bound_args.arguments
        session_id = arguments.get('session_id')
        user_id = arguments.get('user_id')

        if user_id is None:
            raise ValueError(f"Missing 'user_id' in method '{method.__name__}'")
        if session_id is None:
            raise ValueError(f"Missing 'session_id' in method '{method.__name__}'")
        if not isinstance(user_id, str):
            raise ValueError(f"'user_id' must be of type 'str'")
        if not isinstance(session_id, str):
            raise ValueError(f"'session_id' must be of type 'str'")
        if not hasattr(self, "get_authorized_user_id") or not callable(getattr(self, "get_authorized_user_id")):
            raise NotImplementedError(
                f"{self.__class__.__name__} must implement 'get_authorized_user_id'"
            )

        # Get the value of the authorized_user that can access the method. The way to get it depends on the storage type so we have it defined here
        authorized_user_id = self.get_authorized_user_id(session_id)

        # In case we want to load messages for a user with a non initialized session (i.e when first loading the page, we should not throw an unauthorized exception)
        if authorized_user_id is SESSION_NOT_INITIALIZED:
            logger.debug(f"Session '{session_id}' not yet initialized — skipping auth check for method '{method.__name__}'")
            return method(self, *args, **kwargs)

        if authorized_user_id != user_id:
            logger.warning(f"Unauthorized access: user {user_id} to session {session_id} in method '{method.__name__}'")
            raise HTTPException(
                status_code=403,
                detail=f"Unauthorized access: user {user_id} to session {session_id}"
            )

        return method(self, *args, **kwargs)
    return wrapper

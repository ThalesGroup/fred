import time
import logging
import functools
import inspect
from typing import Annotated,get_type_hints

logging.basicConfig(level=logging.INFO)

def monitor_node(func):
    """Decorator to monitor async or sync LangGraph node functions."""
    if inspect.iscoroutinefunction(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            node_name = func.__name__
            logging.info(f"Node '{node_name}' started with args: {args}, kwargs: {kwargs}")
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                elapsed_time = time.time() - start_time
                logging.info(f"Node '{node_name}' completed in {elapsed_time:.2f}s with result: {result}")
                return result
            except Exception as e:
                elapsed_time = time.time() - start_time
                logging.error(f"Node '{node_name}' failed in {elapsed_time:.2f}s with error: {e}")
                raise
        return async_wrapper
    else:
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            node_name = func.__name__
            logging.info(f"Node '{node_name}' started with args: {args}, kwargs: {kwargs}")
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                elapsed_time = time.time() - start_time
                logging.info(f"Node '{node_name}' completed in {elapsed_time:.2f}s with result: {result}")
                return result
            except Exception as e:
                elapsed_time = time.time() - start_time
                logging.error(f"Node '{node_name}' failed in {elapsed_time:.2f}s with error: {e}")
                raise
        return sync_wrapper


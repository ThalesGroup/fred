import logging
import threading

from prometheus_client import start_http_server

logger = logging.getLogger(__name__)


def start_prometheus_exporter(port: int = 8081):
    logger.info(f"Starting Prometheus exporter on port {port}")
    start_http_server(port)

    def collect_metrics():
        while True:
            # Add custom metrics here.
            import time

            time.sleep(5)

    # Launch collect on a specific thread
    t = threading.Thread(target=collect_metrics, daemon=True)
    t.start()

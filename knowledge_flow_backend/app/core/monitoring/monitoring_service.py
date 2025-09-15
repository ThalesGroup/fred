from prometheus_client import (
    CollectorRegistry,
    multiprocess,
    generate_latest,
)

class AppMonitoringMetricsService:
    """
    Service responsible for providing monitoring metrics.
    """

    def __init__(self, registry: CollectorRegistry = None):
        # Si multiprocess est utilisé (Gunicorn, Uvicorn workers, etc.)
        if registry is None:
            registry = CollectorRegistry()
            try:
                multiprocess.MultiProcessCollector(registry)
            except ValueError:
                # Pas en mode multiprocess
                pass
        self.registry = registry

    def get_metrics(self):
        """
        Retourne toutes les métriques sous forme brute (Prometheus format).
        """
        return generate_latest(self.registry)

from typing import List

from langgraph.graph import MessagesState
from pydantic import BaseModel, Field


class KedaScaling(BaseModel):
    """
    Represents a KEDA (Kubernetes Event-driven Autoscaling) `ScaledObject` resource.

    This model defines the KEDA `ScaledObject` configuration, which Kubernetes uses to specify how KEDA should scale
    a target application based on defined triggers (e.g., cron-based scaling or Prometheus-based scaling).
    """

    scaled_object: str = Field(
        description=(
            "The KEDA `ScaledObject` resource, represented as a fully-formed JSON configuration. "
            "This configuration defines the scaling behavior of a target application based on triggers, "
            "such as cron schedules or Prometheus metrics. The JSON structure follows the required format for a Kubernetes `ScaledObject`."
        )
    )

    assumptions: List[str] = Field(
        description=(
            "A list of assumptions made while creating the `ScaledObject`. This may include inferred values for missing parameters "
            "or default configurations applied in the absence of specific inputs. The list will be empty if no assumptions were needed."
        )
    )


class MessagesStateWithFinalStructuredResponse(MessagesState):
    # Final structured response from the agent
    final_response: KedaScaling

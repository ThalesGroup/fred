from typing import List
from app.core.chatbot.chat_schema import ChatMessagePayload
from collections import defaultdict
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def enrich_ChatMessagePayloads_with_latencies(metrics: List[ChatMessagePayload]) -> List[ChatMessagePayload]:
    """
    Enrich metrics in memory by adding latency_seconds between sequential steps
    (by exchange_id and rank). Returns a new flat list of enriched messages.
    """
    by_exchange_id = defaultdict(list)
    logger.info(metrics)
    
    for m in metrics:
        by_exchange_id[m.exchange_id].append(m)

    for exchange_id, messages in by_exchange_id.items():
        messages.sort(key=lambda x: x.rank)

        # Skip if already enriched
        if all("latency_seconds" in (m.metadata or {}) for m in messages[1:]):
            continue

        for i in range(1, len(messages)):
            prev_msg = messages[i - 1]
            curr_msg = messages[i]

            prev_ts = prev_msg.timestamp
            curr_ts = curr_msg.timestamp

            if prev_ts and curr_ts:
                try:
                    prev_dt = datetime.fromisoformat(prev_ts)
                    curr_dt = datetime.fromisoformat(curr_ts)
                    latency = (curr_dt - prev_dt).total_seconds()

                    if latency < 0:
                        logger.warning(
                            f"[MetricStore] Negative latency in exchange_id {exchange_id} "
                            f"between ranks {prev_msg.rank} and {curr_msg.rank}"
                        )

                    if curr_msg.metadata is None:
                        curr_msg.metadata = {}

                    curr_msg.metadata["latency_seconds"] = round(latency, 4)

                except Exception as e:
                    logger.error(
                        f"[MetricStore] Timestamp parsing failed for exchange_id {exchange_id}: {e}"
                    )

    # Flatten list
    enriched_list = []
    for msgs in by_exchange_id.values():
        enriched_list.extend(msgs)

    return enriched_list

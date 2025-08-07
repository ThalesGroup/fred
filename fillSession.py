import uuid
import random
from datetime import datetime, timedelta
from opensearchpy import OpenSearch, RequestsHttpConnection

client = OpenSearch(
    hosts=[{"host": "localhost", "port": 9200}],
    http_auth=("admin", "Azerty123_"),  # update with your creds
    use_ssl=True,
    verify_certs=False,
    connection_class=RequestsHttpConnection,
)

history_index = "history-index"
user_ids = ["alice", "bob", "carol", "david", "eve"]
agents = ["Fred", "Maya", "Rico"]

now = datetime.utcnow()

def generate_fake_message(user_id, agent_name, session_id, exchange_id, rank, offset_minutes):
    timestamp = now - timedelta(minutes=offset_minutes)
    tokens = random.randint(50, 500)
    return {
        "exchange_id": exchange_id,
        "type": "ai",
        "sender": "assistant",
        "content": f"This is a simulated reply for {user_id} from agent {agent_name}.",
        "timestamp": timestamp.isoformat() + "Z",
        "session_id": session_id,
        "rank": rank,
        "metadata": {
            "agent_name": agent_name,
            "token_usage": {
                "input_tokens": tokens // 2,
                "output_tokens": tokens // 2,
                "total_tokens": tokens,
            },
        },
        "subtype": "final"
    }

bulk_body = []

for user_id in user_ids:
    for i in range(3):  # 3 sessions per user
        session_id = str(uuid.uuid4())[:12]
        for j in range(5):  # 5 messages per session
            exchange_id = str(uuid.uuid4())
            message = generate_fake_message(
                user_id=user_id,
                agent_name=random.choice(agents),
                session_id=session_id,
                exchange_id=exchange_id,
                rank=j,
                offset_minutes=random.randint(1, 1440)  # up to 1 day ago
            )
            bulk_body.append({ "index": { "_index": history_index } })
            bulk_body.append(message)

# Perform bulk insert
resp = client.bulk(body=bulk_body)
print("Inserted:", len(resp.get("items", [])), "messages")

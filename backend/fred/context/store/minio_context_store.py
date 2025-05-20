import logging
from io import BytesIO
from typing import Optional
from context.store.base_context_store import BaseContextStore
from minio import Minio
from minio.error import S3Error


logger = logging.getLogger(__name__)

class MinIOContextStore(BaseContextStore):
    """
    MinIO implementation of the context store. Stores agent context as text files in a bucket.
    """

    def __init__(self, client: Minio, bucket_name: str):
        self.client = client
        self.bucket_name = bucket_name
        self.prefix = "context/"

        # Ensure the bucket exists
        if not self.client.bucket_exists(bucket_name):
            self.client.make_bucket(bucket_name)
            logger.info(f"🪣 Bucket '{bucket_name}' created successfully for contexts.")

    def _object_name(self, agent_id: str) -> str:
        return f"{self.prefix}{agent_id}.txt"

    def get_context(self, agent_id: str) -> Optional[str]:
        """
        Retrieve the context associated with the given agent ID.
        Returns None if context does not exist.
        """
        object_name = self._object_name(agent_id)
        try:
            response = self.client.get_object(self.bucket_name, object_name)
            context = response.read().decode("utf-8")
            logger.info(f"📥 Retrieved context for agent '{agent_id}'.")
            return context
        except S3Error as e:
            if e.code == "NoSuchKey":
                logger.warning(f"⚠️ No context found for agent '{agent_id}'.")
                return None
            logger.error(f"❌ Failed to fetch context for '{agent_id}': {e}")
            raise

    def set_context(self, agent_id: str, context: str) -> None:
        """
        Save the given context for the specified agent.
        """
        object_name = self._object_name(agent_id)
        try:
            data = context.encode("utf-8")
            self.client.put_object(
                bucket_name=self.bucket_name,
                object_name=object_name,
                data=BytesIO(data),
                length=len(data),
                content_type="text/plain"
            )
            logger.info(f"💾 Context stored for agent '{agent_id}' as '{object_name}'.")
        except S3Error as e:
            logger.error(f"❌ Failed to store context for '{agent_id}': {e}")
            raise

    def delete_context(self, agent_id: str) -> None:
        """
        Delete the context associated with the given agent ID.
        """
        object_name = self._object_name(agent_id)
        try:
            self.client.remove_object(self.bucket_name, object_name)
            logger.info(f"🗑️ Deleted context for agent '{agent_id}' ({object_name}).")
        except S3Error as e:
            if e.code == "NoSuchKey":
                logger.warning(f"⚠️ Tried to delete non-existing context for '{agent_id}'.")
            else:
                logger.error(f"❌ Failed to delete context for '{agent_id}': {e}")
                raise

import logging
import json
import io
import os
import pathlib
import uuid
from typing import List, Dict, Optional
from minio import Minio

logger = logging.getLogger(__name__)

class ContextService:
    """Service to manage agent contexts with adaptive storage (MinIO or local)"""

    def __init__(self, minio_client: Optional[Minio] = None, bucket_name: str = "agent-contexts", local_base_dir: Optional[pathlib.Path] = None):
        """
        Initialize the adaptive context service
        """
        self.minio_client = minio_client
        self.bucket_name = bucket_name
        
        # Configure local storage path (always needed, even with MinIO for fallback)
        if local_base_dir is None:
            try:
                from context.context_storage_settings import context_storage_settings
                storage_path = context_storage_settings.get_storage_path()
                if storage_path and isinstance(storage_path, str):
                    self.local_base_dir = pathlib.Path(storage_path)
                else:
                    # Fallback if get_storage_path() returns None or non-string
                    logger.warning("Invalid storage path from settings, using default")
                    self.local_base_dir = pathlib.Path(os.path.expanduser("~/.fred/context-store"))
            except Exception as e:
                # Ultimate fallback
                logger.error(f"Error setting local path: {e}")
                self.local_base_dir = pathlib.Path(os.path.expanduser("~/.fred/context-store"))
        else:
            self.local_base_dir = local_base_dir
        
        # Initialize storage
        if self.minio_client is None:
            try:
                self._ensure_local_dir_exists()
            except Exception as e:
                logger.exception(f"Failed to create local directory: {e}")
        else:
            try:
                self._ensure_bucket_exists()
            except Exception as e:
                logger.error(f"Failed to ensure MinIO bucket exists: {e}")
                logger.warning("MinIO operations may fail")
    
    def _ensure_local_dir_exists(self):
        """Ensure local directory exists"""
        try:
            self.local_base_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error(f"Error creating local directory: {e}")
            raise
    
    def _ensure_bucket_exists(self):
        """Ensure MinIO bucket exists"""
        if self.minio_client is None:
            return
            
        try:
            if not self.minio_client.bucket_exists(self.bucket_name):
                self.minio_client.make_bucket(self.bucket_name)
                logger.info(f"Created MinIO bucket: {self.bucket_name}")
        except Exception as e:
            logger.error(f"Error checking/creating bucket: {str(e)}")
            raise
    
    def _get_agent_object_name(self, agent_name: str) -> str:
        """Generate object name for agent contexts"""
        return f"{agent_name.lower().replace(' ', '_')}_contexts.json"
    
    def _get_agent_file_path(self, agent_name: str) -> pathlib.Path:
        """Generate file path for agent contexts"""
        return self.local_base_dir / self._get_agent_object_name(agent_name)
    
    def get_contexts(self, agent_name: str) -> List[Dict]:
        """Retrieve all contexts for an agent"""
        if self.minio_client is None:
            return self._get_contexts_local(agent_name)
        else:
            return self._get_contexts_minio(agent_name)
    
    def _get_contexts_local(self, agent_name: str) -> List[Dict]:
        """Retrieve contexts from local files"""
        file_path = self._get_agent_file_path(agent_name)
        try:
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return []
        except Exception as e:
            logger.error(f"Error retrieving local contexts: {str(e)}")
            raise
    
    def _get_contexts_minio(self, agent_name: str) -> List[Dict]:
        """Retrieve contexts from MinIO"""
        object_name = self._get_agent_object_name(agent_name)
        try:
            try:
                response = self.minio_client.get_object(self.bucket_name, object_name)
                data = json.loads(response.read().decode('utf-8'))
                response.close()
                return data
            except Exception as e:
                # Log the specific error but return empty list
                logger.debug(f"No contexts found or error accessing MinIO: {str(e)}")
                return []
        except Exception as e:
            logger.error(f"Error retrieving MinIO contexts: {str(e)}")
            raise
    
    def save_context(self, agent_name: str, context: Dict) -> Dict:
        """Save a context for an agent (create or update)"""
        contexts = self.get_contexts(agent_name)
        
        # Check if update or create
        if "id" in context and context["id"]:
            # Try to update existing context
            updated = False
            for i, existing in enumerate(contexts):
                if existing["id"] == context["id"]:
                    contexts[i] = context
                    updated = True
                    break
            
            # If ID not found, add as new
            if not updated:
                new_context = {
                    "id": context["id"],
                    "title": context["title"],
                    "content": context["content"]
                }
                contexts.append(new_context)
                context = new_context
        else:
            # Create new context with generated ID
            new_context = {
                "id": str(uuid.uuid4()),
                "title": context["title"],
                "content": context["content"]
            }
            contexts.append(new_context)
            context = new_context
            
        # Save to appropriate storage
        if self.minio_client is None:
            self._save_contexts_local(agent_name, contexts)
        else:
            self._save_contexts_minio(agent_name, contexts)
            
        return context
    
    def delete_context(self, agent_name: str, context_id: str) -> bool:
        """Delete a context for an agent"""
        contexts = self.get_contexts(agent_name)
        initial_count = len(contexts)
        
        # Filter out context with given ID
        contexts = [c for c in contexts if c["id"] != context_id]
        
        # If no change, nothing was deleted
        if len(contexts) == initial_count:
            return False
            
        # Save updated contexts list
        if self.minio_client is None:
            self._save_contexts_local(agent_name, contexts)
        else:
            self._save_contexts_minio(agent_name, contexts)
            
        return True
    
    def _save_contexts_local(self, agent_name: str, contexts: List[Dict]):
        """Save contexts to local file"""
        file_path = self._get_agent_file_path(agent_name)
        try:
            # Safe file write (temp file then rename)
            temp_file = file_path.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(contexts, f, ensure_ascii=False, indent=2)
            temp_file.replace(file_path)
        except Exception as e:
            logger.error(f"Error saving to local storage: {str(e)}")
            raise
    
    def _save_contexts_minio(self, agent_name: str, contexts: List[Dict]):
        """Save contexts to MinIO"""
        object_name = self._get_agent_object_name(agent_name)
        try:
            # Prepare and upload data
            json_data = json.dumps(contexts, ensure_ascii=False)
            data = io.BytesIO(json_data.encode('utf-8'))
            data_length = len(json_data.encode('utf-8'))
            
            self.minio_client.put_object(
                self.bucket_name,
                object_name,
                data,
                length=data_length,
                content_type="application/json"
            )
        except Exception as e:
            logger.error(f"Error saving to MinIO storage: {str(e)}")
            raise
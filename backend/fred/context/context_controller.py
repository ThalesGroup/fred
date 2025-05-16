import logging
from fastapi import (
    APIRouter,
    HTTPException,
    status,
)
from typing import List, Optional
from pydantic import BaseModel
from fred.application_context import ApplicationContext

# Logger configuration
logger = logging.getLogger(__name__)

# Data models
class ContextCardRequest(BaseModel):
    id: Optional[str] = None
    title: str
    content: str

class ContextCardResponse(BaseModel):
    id: str
    title: str
    content: str

class StatusResponse(BaseModel):
    status: str
    message: Optional[str] = None

class ContextController:
    """
    This controller is responsible for handling the context management endpoints.
    It provides API endpoints for creating, reading, updating, and deleting 
    context cards used by agents to enhance their responses.
    """

    def __init__(self, app: APIRouter):
        """
        Initialize the context controller with the application.
        
        Args:
            app: The FastAPI router to register endpoints on
        """
        # Get the ApplicationContext
        app_context = ApplicationContext._instance
        
        try:
            # Get a fresh context service to ensure correct storage type
            logger.info("Retrieving context service from ApplicationContext")
            self.context_service = app_context.get_context_service()
            
            # Log the storage type being used
            storage_type = "MinIO" if hasattr(self.context_service, "minio_client") and self.context_service.minio_client else "Local"
            logger.info(f"Initialized ContextController with {storage_type} storage")
        except Exception as e:
            logger.error(f"Failed to initialize context service: {e}")
            raise RuntimeError(f"Could not initialize ContextController: {e}")

        # FastAPI tags for documentation
        fastapi_tags = ["Context Management"]

        # Endpoint definitions
        @app.get(
            "/contexts/{agent_name}",
            tags=fastapi_tags,
            response_model=List[ContextCardResponse],
            status_code=status.HTTP_200_OK,
            description="Get all contexts for a specific agent",
            summary="Get agent contexts"
        )
        async def get_agent_contexts(
            agent_name: str,
        ):
            """
            Get all contexts for a specific agent
            """
            try:
                # Get fresh instance to ensure proper storage
                fresh_context_service = app_context.get_context_service()
                
                # Ensure we're using the storage specified in configuration
                logger.info(f"Retrieving contexts for {agent_name}")
                contexts = fresh_context_service.get_contexts(agent_name)
                logger.info(f"Found {len(contexts)} contexts for {agent_name}")
                return contexts
            except Exception as e:
                logger.error(f"Error retrieving contexts for {agent_name}: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")
        
        @app.post(
            "/contexts/{agent_name}",
            tags=fastapi_tags,
            response_model=ContextCardResponse,
            status_code=status.HTTP_200_OK,
            description="Create or update a context for an agent",
            summary="Create or update a context"
        )
        async def create_or_update_context(
            agent_name: str, 
            context_request: ContextCardRequest,
        ):
            """
            Create or update a context for an agent
            """
            try:
                # Get fresh instance to ensure proper storage
                fresh_context_service = app_context.get_context_service()
                
                logger.info(f"Saving context for {agent_name}: {context_request.title}")
                context_dict = context_request.model_dump(exclude_unset=True)
                
                # Save context using the fresh service
                result = fresh_context_service.save_context(agent_name, context_dict)
                logger.info(f"Saved context with ID: {result['id']}")
                
                return result
            except Exception as e:
                logger.error(f"Error saving context for {agent_name}: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")
        
        @app.delete(
            "/contexts/{agent_name}/{context_id}",
            tags=fastapi_tags,
            response_model=StatusResponse,
            status_code=status.HTTP_200_OK,
            description="Delete a context for an agent",
            summary="Delete a context"
        )
        async def delete_context(
            agent_name: str, 
            context_id: str,
        ):
            """
            Delete a context for an agent
            """
            try:
                # Get fresh instance to ensure proper storage
                fresh_context_service = app_context.get_context_service()
                
                logger.info(f"Deleting context {context_id} for {agent_name}")
                success = fresh_context_service.delete_context(agent_name, context_id)
                if not success:
                    logger.warning(f"Context {context_id} not found for {agent_name}")
                    raise HTTPException(status_code=404, detail="Context not found")
                
                logger.info(f"Successfully deleted context {context_id} for {agent_name}")
                return StatusResponse(status="success", message="Context successfully deleted")
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error deleting context {context_id} for {agent_name}: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")
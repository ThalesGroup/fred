
from anyio import to_thread
import logging
from fastapi import APIRouter, Depends, HTTPException
from fred_core import KeycloakUser, get_current_user
from pydantic import BaseModel

from app.application_context import get_default_model

logger = logging.getLogger(__name__)

class PromptCompleteRequest(BaseModel):
    prompt: str
    temperature: float | None = 0.3
    max_tokens: int | None = 512
    model: str | None = None

class PromptCompleteResponse(BaseModel):
    prompt: str
    completion: str


class PromptController:
    def __init__(self, router: APIRouter):
        def handle_exception(e: Exception) -> HTTPException:
            logger.error(f"Internal server error: {e}", exc_info=True)
            return HTTPException(status_code=500, detail="Internal server error")

        self._register_routes(router, handle_exception)

    def _register_routes(self, router: APIRouter, handle_exception):
        @router.post(
            "/prompts/complete",
            tags=["Prompts"],
            response_model=PromptCompleteResponse,
            summary="Complete a raw prompt string with AI",
            description="Returns an AI-completed version of the provided prompt text."
        )
        async def complete_prompt(
            req: PromptCompleteRequest,
            user: KeycloakUser = Depends(get_current_user),
        ) -> PromptCompleteResponse:
            try:
                # Build a simple instruction (feel free to tweak)
                instruction = (
                    "Rewrite and complete the following prompt so it is clear, specific, and well-structured. "
                    "Keep it concise and actionable. Return ONLY the improved prompt.\n\n"
                    f"Original prompt:\n{req.prompt}"
                )

                # Get model and apply optional params if supported
                model = get_default_model()
                bind_kwargs = {k: v for k, v in {
                    "temperature": req.temperature,
                    "max_tokens": req.max_tokens,
                    "model": req.model,
                }.items() if v is not None}

                if bind_kwargs and hasattr(model, "bind"):
                    model = model.bind(**bind_kwargs)

                # Run blocking .invoke in a worker thread to avoid blocking the event loop
                def _invoke():
                    out = model.invoke(instruction)
                    return getattr(out, "content", str(out))

                completion = await to_thread.run_sync(_invoke)

                return PromptCompleteResponse(prompt=req.prompt, completion=completion)
            except Exception as e:
                raise handle_exception(e)

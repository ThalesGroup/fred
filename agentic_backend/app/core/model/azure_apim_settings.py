# app/config/llm_azure_apim_settings.py
from pydantic_settings import BaseSettings
from pydantic import Field


class AzureApimSettings(BaseSettings):
    azure_tenant_id: str = Field(..., validation_alias="AZURE_TENANT_ID")
    azure_client_id: str = Field(..., validation_alias="AZURE_CLIENT_ID")
    azure_client_secret: str = Field(..., validation_alias="AZURE_CLIENT_SECRET")
    azure_client_scope: str = Field(..., validation_alias="AZURE_CLIENT_SCOPE")

    azure_apim_base_url: str = Field(..., validation_alias="AZURE_APIM_BASE_URL")
    azure_resource_path_llm: str = Field(..., validation_alias="AZURE_RESOURCE_PATH_LLM")
    azure_api_version: str = Field(..., validation_alias="AZURE_API_VERSION")
    azure_apim_key: str = Field(..., validation_alias="AZURE_APIM_KEY")
    azure_deployment_llm: str = Field(..., validation_alias="AZURE_DEPLOYMENT_LLM")

    model_config = {
        "extra": "ignore"
    }

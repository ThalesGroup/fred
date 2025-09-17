import logging

from azure.identity import ClientSecretCredential
from langchain_openai import AzureChatOpenAI

from app.core.model.azure_apim_settings import AzureApimSettings

logger = logging.getLogger(__name__)


class AzureApimModel:
    def __init__(self, settings: AzureApimSettings = None):
        self.settings = settings or AzureApimSettings()

    def _get_token(self) -> str:
        credential = ClientSecretCredential(
            tenant_id=self.settings.azure_tenant_id,
            client_id=self.settings.azure_client_id,
            client_secret=self.settings.azure_client_secret,
        )
        return credential.get_token(self.settings.azure_client_scope).token

    def get_llm(self) -> AzureChatOpenAI:
        logger.info("✅ Initializing Azure APIM Chat LLM")
        token = self._get_token()

        full_url = (
            f"{self.settings.azure_apim_base_url.rstrip()}"
            f"{self.settings.azure_resource_path_llm}"
            f"/deployments/{self.settings.azure_deployment_llm}/chat/completions"
            f"?api-version={self.settings.azure_api_version}"
        )

        return AzureChatOpenAI(
            azure_endpoint=full_url,
            openai_api_version=self.settings.azure_api_version,
            deployment_name=self.settings.azure_deployment_llm,
            openai_api_key=token,
            openai_api_type="azure",
            default_headers={
                "TrustNest-Apim-Subscription-Key": self.settings.azure_apim_key
            },
            temperature=0,
            max_retries=2,
            timeout=60,
        )

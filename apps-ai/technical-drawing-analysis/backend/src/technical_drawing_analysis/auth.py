from azure.core.credentials import TokenCredential
from azure.identity import AzureCliCredential
from azure.identity import AzureDeveloperCliCredential
from azure.identity import AzurePowerShellCredential
from azure.identity import ChainedTokenCredential
from azure.identity import DefaultAzureCredential

from technical_drawing_analysis.settings import get_settings


def _default_credential_kwargs(tenant_id: str | None) -> dict[str, object]:
    if not tenant_id:
        return {}
    return {
        "visual_studio_code_tenant_id": tenant_id,
        "shared_cache_tenant_id": tenant_id,
        "interactive_browser_tenant_id": tenant_id,
        "broker_tenant_id": tenant_id,
    }


def _azure_cli_credential_kwargs(
    tenant_id: str | None,
    subscription_id: str | None,
) -> dict[str, str]:
    if subscription_id:
        return {"subscription": subscription_id}
    if tenant_id:
        return {"tenant_id": tenant_id}
    return {}


def _tenant_credential_kwargs(tenant_id: str | None) -> dict[str, str]:
    if tenant_id:
        return {"tenant_id": tenant_id}
    return {}


def create_credential() -> TokenCredential:
    settings = get_settings()
    tenant_id = settings.azure_tenant_id
    subscription_id = settings.azure_ai_subscription_id
    if tenant_id or subscription_id:
        return ChainedTokenCredential(
            AzureCliCredential(**_azure_cli_credential_kwargs(tenant_id, subscription_id)),
            AzureDeveloperCliCredential(**_tenant_credential_kwargs(tenant_id)),
            AzurePowerShellCredential(**_tenant_credential_kwargs(tenant_id)),
            DefaultAzureCredential(
                exclude_cli_credential=True,
                exclude_developer_cli_credential=True,
                exclude_powershell_credential=True,
                **_default_credential_kwargs(tenant_id),
            ),
        )
    return DefaultAzureCredential()


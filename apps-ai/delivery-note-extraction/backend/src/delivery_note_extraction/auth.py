from azure.core.credentials import TokenCredential
from azure.identity import AzureCliCredential
from azure.identity import AzureDeveloperCliCredential
from azure.identity import AzurePowerShellCredential
from azure.identity import ChainedTokenCredential
from azure.identity import DefaultAzureCredential

from delivery_note_extraction.settings import get_settings


def _default_credential_kwargs(tenant_id: str | None) -> dict[str, object]:
    if not tenant_id:
        return {}
    return {
        "visual_studio_code_tenant_id": tenant_id,
        "shared_cache_tenant_id": tenant_id,
        "interactive_browser_tenant_id": tenant_id,
        "broker_tenant_id": tenant_id,
    }


def create_credential() -> TokenCredential:
    settings = get_settings()
    tenant_id = settings.azure_tenant_id
    subscription_id = settings.azure_ai_subscription_id
    if tenant_id or subscription_id:
        if subscription_id:
            azure_cli = AzureCliCredential(subscription=subscription_id)
        elif tenant_id:
            azure_cli = AzureCliCredential(tenant_id=tenant_id)
        else:
            azure_cli = AzureCliCredential()
        if tenant_id:
            azure_dev_cli = AzureDeveloperCliCredential(tenant_id=tenant_id)
            azure_powershell = AzurePowerShellCredential(tenant_id=tenant_id)
        else:
            azure_dev_cli = AzureDeveloperCliCredential()
            azure_powershell = AzurePowerShellCredential()
        return ChainedTokenCredential(
            azure_cli,
            azure_dev_cli,
            azure_powershell,
            DefaultAzureCredential(
                exclude_cli_credential=True,
                exclude_developer_cli_credential=True,
                exclude_powershell_credential=True,
                **_default_credential_kwargs(tenant_id),
            ),
        )
    return DefaultAzureCredential()

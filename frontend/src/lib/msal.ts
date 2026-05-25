import { PublicClientApplication, Configuration, LogLevel } from "@azure/msal-browser";

// Allow users to override the client ID via URL parameter: ?clientId=xxx
function getClientId(): string {
  if (typeof window !== "undefined") {
    const params = new URLSearchParams(window.location.search);
    const override = params.get("clientId");
    if (override) {
      localStorage.setItem("fabric_demo_clientId", override);
      return override;
    }
    const saved = localStorage.getItem("fabric_demo_clientId");
    if (saved) return saved;
  }
  return process.env.NEXT_PUBLIC_AZURE_CLIENT_ID || "";
}

const clientId = getClientId();
const tenantId = process.env.NEXT_PUBLIC_AZURE_TENANT_ID || "common";

const msalConfig: Configuration = {
  auth: {
    clientId,
    authority: `https://login.microsoftonline.com/${tenantId}`,
    redirectUri: typeof window !== "undefined" ? `${window.location.origin}/` : "http://localhost:3000/",
    postLogoutRedirectUri: typeof window !== "undefined" ? window.location.origin : "http://localhost:3000",
  },
  cache: {
    cacheLocation: "localStorage",
  },
  system: {
    loggerOptions: {
      logLevel: LogLevel.Warning,
    },
  },
};

export const msalInstance = new PublicClientApplication(msalConfig);

// All Fabric API scopes requested at sign-in so consent happens once upfront.
// These must be added to the app registration under:
//   API permissions → Power BI Service → Delegated
// Required: Workspace.ReadWrite.All, Item.ReadWrite.All,
//           Connection.ReadWrite.All, OneLake.ReadWrite.All
export const fabricScopes = [
  "https://api.fabric.microsoft.com/Workspace.ReadWrite.All",
  "https://api.fabric.microsoft.com/Item.ReadWrite.All",
  "https://api.fabric.microsoft.com/Connection.ReadWrite.All",
  "https://api.fabric.microsoft.com/OneLake.ReadWrite.All",
];

// Scopes needed for OneLake (storage)
export const storageScopes = ["https://storage.azure.com/.default"];

// Scopes needed for Azure Resource Manager (ARM) — used for ADLS Gen2 provisioning
export const managementScopes = ["https://management.azure.com/user_impersonation"];



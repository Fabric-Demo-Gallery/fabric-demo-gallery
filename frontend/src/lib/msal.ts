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

// Scopes needed for Fabric API
// Using .default avoids admin consent requirements — Fabric handles authorization
// at the resource level based on the user's actual permissions
export const fabricScopes = [
  "https://api.fabric.microsoft.com/.default",
];

// Scopes needed for OneLake (storage)
export const storageScopes = ["https://storage.azure.com/.default"];

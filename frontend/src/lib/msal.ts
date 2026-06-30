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

// Popup/iframe token flows return to a minimal static page (public/auth.html)
// instead of the full SPA. The window that opens the popup reads the auth response
// off the popup's URL and closes it; loading the entire app in the popup raced that
// close and stranded it on "Completing sign-in\u2026" even though the opener got the
// token. A blank same-origin page is read + closed instantly. The global
// redirectUri stays `/` because the full-page loginRedirect must land on the app.
export const popupRedirectUri =
  typeof window !== "undefined" ? `${window.location.origin}/auth.html` : "http://localhost:3000/auth.html";

// All Fabric API scopes requested at sign-in so consent happens once upfront.
// These must be added to the app registration under:
//   API permissions → Power BI Service → Delegated
// Required: Workspace.ReadWrite.All, Item.ReadWrite.All,
//           Connection.ReadWrite.All, OneLake.ReadWrite.All
// NOTE: KQLDatabase.ReadWrite.All is intentionally NOT requested at sign-in. It's
// only needed for the optional RTI history seed, so it's acquired incrementally
// via `kustoScopes` / getKustoToken. Keeping the up-front consent set small avoids
// "Need admin approval" in tenants that restrict consent for unverified apps —
// an expanding sign-in scope set forces re-consent that such tenants block.
export const fabricScopes = [
  "https://api.fabric.microsoft.com/Workspace.ReadWrite.All",
  "https://api.fabric.microsoft.com/Item.ReadWrite.All",
  "https://api.fabric.microsoft.com/Connection.ReadWrite.All",
  "https://api.fabric.microsoft.com/OneLake.ReadWrite.All",
];

// Separate OneLake scope — needs its own token for shortcut creation (OneLake.ReadWrite.All)
export const oneLakeScopes = ["https://api.fabric.microsoft.com/OneLake.ReadWrite.All"];

// Scopes needed for OneLake (storage)
export const storageScopes = ["https://storage.azure.com/.default"];

// Scopes needed for Azure Resource Manager (ARM) — used for ADLS Gen2 provisioning
export const managementScopes = ["https://management.azure.com/user_impersonation"];

// Azure AI Search data-plane — Foundry IQ knowledge source + base (fabric-foundry-agent scenario)
export const searchScopes = ["https://search.azure.com/user_impersonation"];

// Microsoft Foundry Agent Service data-plane — create the grounded agent.
// user_impersonation (not .default) so the consent popup can grant it dynamically.
export const agentScopes = ["https://ai.azure.com/user_impersonation"];

// Scope used to attempt the optional historical data seed via the Eventhouse/KQL
// data-plane. NOTE: `kusto.fabric.microsoft.com` is not registered as a resource
// principal in every tenant (causes AADSTS500011 at sign-in), so we request the
// Fabric-audience KQLDatabase scope instead. The table itself is created via the
// Fabric definition API (no data-plane token needed), and the live Eventstream is
// the primary data source — so a failed/again-skipped seed is non-fatal.
export const kustoScopes = ["https://api.fabric.microsoft.com/KQLDatabase.ReadWrite.All"];



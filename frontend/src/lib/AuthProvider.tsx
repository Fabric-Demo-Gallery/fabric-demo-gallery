"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { type AccountInfo } from "@azure/msal-browser";
import { msalInstance, popupRedirectUri, fabricScopes, storageScopes, managementScopes, searchScopes, agentScopes, kustoScopes } from "@/lib/msal";

// Local dev mode: when no AZURE_CLIENT_ID is configured, skip MSAL entirely.
// The backend falls back to `az login` (az CLI) tokens automatically.
const IS_DEV_MODE = !process.env.NEXT_PUBLIC_AZURE_CLIENT_ID;

// interactive: allow popup on silent failure (default true).
// allowRedirect: allow full-page redirect as a last resort if the popup fails
// (default true). Set false for optional/best-effort tokens so a consent failure
// throws (and the caller skips it) instead of navigating the whole page away.
// forceRefresh: bypass MSAL's access-token cache and mint a fresh token from the
// refresh token. Use before a long-running deploy so a near-expiry cached token
// doesn't expire mid-deploy.
type TokenOptions = { interactive?: boolean; allowRedirect?: boolean; forceRefresh?: boolean };

const DEV_ACCOUNT = {
  homeAccountId: "dev-local",
  environment: "local",
  tenantId: "local",
  username: "dev@local",
  localAccountId: "dev-local",
  name: "Dev Mode (az CLI)",
} as AccountInfo;

interface AuthState {
  initialized: boolean;
  account: AccountInfo | null;
  authError: string;
  login: () => Promise<void>;
  logout: () => void;
  getFabricToken: (options?: TokenOptions) => Promise<string>;
  getStorageToken: (options?: TokenOptions) => Promise<string>;
  getManagementToken: (options?: TokenOptions) => Promise<string>;
  getSearchToken: (options?: TokenOptions) => Promise<string>;
  getAgentToken: (options?: TokenOptions) => Promise<string>;
  getKustoToken: () => Promise<string>;
  /** Pre-consent the Foundry data-plane resources (Search + Agent) in one popup.
   * Resolves "ok" when tokens are silently available or consent just completed;
   * "cached-skip" when a prior consent exists but silent acquisition is blocked
   * (CA policies / guest accounts) — the deploy proceeds on backend fallbacks and
   * the UI should offer the re-authorize action. */
  ensureFoundryConsent: () => Promise<"ok" | "cached-skip">;
  /** Clear the per-account "consent completed" flag so the next deploy re-runs the
   * consent popup — escape hatch for tenants whose CA policies block silent tokens
   * (they'd otherwise be stuck in degraded agent deploys forever). */
  resetFoundryConsent: () => void;
}

const AuthContext = createContext<AuthState>({
  initialized: false,
  account: null,
  authError: "",
  login: async () => {},
  logout: () => {},
  getFabricToken: async () => "",
  getStorageToken: async () => "",
  getManagementToken: async () => "",
  getSearchToken: async () => "",
  getAgentToken: async () => "",
  getKustoToken: async () => "",
  ensureFoundryConsent: async () => "ok" as const,
  resetFoundryConsent: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [initialized, setInitialized] = useState(IS_DEV_MODE); // dev mode starts ready
  const [account, setAccount] = useState<AccountInfo | null>(IS_DEV_MODE ? DEV_ACCOUNT : null);
  const [authError, setAuthError] = useState<string>("");

  useEffect(() => {
    if (IS_DEV_MODE) return; // skip MSAL entirely in local dev mode

    msalInstance.initialize().then(async () => {
      // Handle redirect response (if coming back from login)
      try {
        const response = await msalInstance.handleRedirectPromise();
        if (response?.account) {
          msalInstance.setActiveAccount(response.account);
          setAccount(response.account);
        }
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : String(e);
        console.error("MSAL redirect error:", msg, e);
        setAuthError(msg);
      }

      // Always check cached accounts
      const accounts = msalInstance.getAllAccounts();
      if (accounts.length > 0 && !account) {
        msalInstance.setActiveAccount(accounts[0]);
        setAccount(accounts[0]);
      }
      setInitialized(true);
    }).catch((e) => {
      console.error("MSAL init error:", e);
      setAuthError(e instanceof Error ? e.message : String(e));
      setInitialized(true);
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = useCallback(async () => {
    if (IS_DEV_MODE) return; // already "logged in" via az CLI in dev mode
    setAuthError("");
    try {
      // MSAL v3 requires initialize() before any interactive call. It's idempotent,
      // so awaiting it here makes a click that lands before the mount-time init
      // finishes still work — otherwise loginRedirect throws
      // "uninitialized_public_client_application" and the button silently no-ops.
      await msalInstance.initialize();
      await msalInstance.loginRedirect({
        scopes: fabricScopes,
      });
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      console.error("Login failed:", e);
      // A prior interrupted redirect can leave MSAL's interaction flag set, so
      // loginRedirect throws "interaction_in_progress" and nothing happens. Surface
      // it instead of swallowing, and tell the user to refresh — a page load runs
      // handleRedirectPromise() which clears the stuck flag.
      if (/interaction_in_progress/i.test(msg)) {
        setAuthError("A previous sign-in didn't finish. Please refresh the page, then click Sign in again.");
      } else {
        setAuthError(`Sign-in couldn't start: ${msg}. Please refresh and try again.`);
      }
    }
  }, []);

  const logout = useCallback(() => {
    if (IS_DEV_MODE) return;
    msalInstance.logoutRedirect();
    setAccount(null);
  }, []);

  const getToken = useCallback(
    async (scopes: string[], options?: TokenOptions): Promise<string> => {
      if (IS_DEV_MODE) return ""; // backend uses az CLI token in dev mode
      const interactive = options?.interactive !== false;
      const allowRedirect = options?.allowRedirect !== false;
      if (!account) throw new Error("Not signed in");
      try {
        const result = await msalInstance.acquireTokenSilent({
          scopes,
          account,
          forceRefresh: options?.forceRefresh,
        });
        return result.accessToken;
      } catch (e) {
        if (!interactive) {
          throw e;
        }
        // Any failure (interaction required, timeout, etc.) → use popup
        try {
          const result = await msalInstance.acquireTokenPopup({ scopes, redirectUri: popupRedirectUri });
          return result.accessToken;
        } catch (popupErr) {
          console.error("Token popup failed:", popupErr);
          // For optional/best-effort tokens, surface the error so the caller can
          // skip it. A full-page redirect here would unload the deploy and trip
          // MSAL's no_token_request_cache_error on the way back.
          if (!allowRedirect) {
            throw popupErr instanceof Error ? popupErr : new Error(String(popupErr));
          }
          await msalInstance.acquireTokenRedirect({ scopes });
          throw new Error("Redirecting for token...");
        }
      }
    },
    [account]
  );

  const getFabricToken = useCallback(
    (options?: TokenOptions) => getToken(fabricScopes, options),
    [getToken]
  );

  const getStorageToken = useCallback(
    (options?: TokenOptions) => getToken(storageScopes, options),
    [getToken]
  );

  const getManagementToken = useCallback(
    (options?: TokenOptions) => getToken(managementScopes, options),
    [getToken]
  );

  const getSearchToken = useCallback(
    (options?: TokenOptions) => getToken(searchScopes, options),
    [getToken]
  );

  const getAgentToken = useCallback(
    (options?: TokenOptions) => getToken(agentScopes, options),
    [getToken]
  );

  const getKustoToken = useCallback(
    () => getToken(kustoScopes),
    [getToken]
  );

  // Pre-acquire the Foundry data-plane consent (Azure AI Search + Foundry Agent)
  // in ONE popup, tied to a fresh user gesture. Browsers only allow a popup
  // within the activation window of a click, so requesting these late in the
  // deploy flow (after several awaits) gets the popup blocked — which is why the
  // knowledge-base + agent steps silently skipped. Calling this first, straight
  // off the Deploy click, fires a single consent popup covering BOTH resources;
  // the deploy then reads each token silently with no further popup.
  const ensureFoundryConsent = useCallback(async (): Promise<"ok" | "cached-skip"> => {
    if (IS_DEV_MODE || !account) return "ok";
    // Remember a completed consent per account. Some tenants grant the consent
    // but still refuse SILENT ai.azure.com tokens afterwards (CA policies,
    // guest accounts). Gating the popup on silent-acquire alone then re-prompts
    // on EVERY deploy — and each popup burns the click's activation window, so
    // any later token popup in the deploy gets blocked and escalates to a
    // full-page redirect that kills the deploy UI.
    const consentKey = `foundry_consent_${account.homeAccountId}`;
    try {
      // Already consented (e.g. a prior deploy)? Gate on the AGENT scope — it's the
      // one that actually blocks agent creation, and it's granted together with
      // Search in the popup below, so a missing agent scope must re-trigger consent.
      await msalInstance.acquireTokenSilent({ scopes: agentScopes, account });
      localStorage.setItem(consentKey, "1");
      return "ok";
    } catch {
      // Silent failed — but if this account already completed the consent popup
      // once, don't re-prompt: the deploy degrades the KB/agent steps to manual
      // follow-ups instead (by design), which beats a popup storm. Report it so
      // the UI can surface the re-authorize action (otherwise the user has no
      // visible path out of the degraded mode).
      if (localStorage.getItem(consentKey) === "1") return "cached-skip";
      // One interactive consent covering EVERY resource the deploy needs: Search
      // (primary token) + Foundry Agent + Storage + ARM via extraScopesToConsent.
      // First-time users previously consented only Search+Agent here, so the
      // storage/management tokens later in the deploy still needed interaction —
      // but the click's popup-activation window was already spent, the second
      // popup got blocked, and the deploy died with a cryptic auth error that
      // looked like it needed a refresh/re-sign-in. Consenting everything in
      // this one popup makes every later acquire silent.
      await msalInstance.acquireTokenPopup({
        scopes: searchScopes,
        extraScopesToConsent: [...agentScopes, ...storageScopes, ...managementScopes],
        redirectUri: popupRedirectUri,
      });
      localStorage.setItem(consentKey, "1");
      return "ok";
    }
  }, [account]);

  const resetFoundryConsent = useCallback(() => {
    if (!account) return;
    localStorage.removeItem(`foundry_consent_${account.homeAccountId}`);
  }, [account]);

  return (
    <AuthContext.Provider
      value={{ initialized, account, authError, login, logout, getFabricToken, getStorageToken, getManagementToken, getSearchToken, getAgentToken, getKustoToken, ensureFoundryConsent, resetFoundryConsent }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}

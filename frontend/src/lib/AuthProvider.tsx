"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import {
  InteractionRequiredAuthError,
  BrowserUtils,
  type AccountInfo,
} from "@azure/msal-browser";
import { msalInstance, fabricScopes, storageScopes, managementScopes, searchScopes, agentScopes, kustoScopes } from "@/lib/msal";

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
  /** Pre-consent the Foundry data-plane resources (Search + Agent) in one popup. */
  ensureFoundryConsent: () => Promise<void>;
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
  ensureFoundryConsent: async () => {},
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
          const result = await msalInstance.acquireTokenPopup({ scopes });
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
  const ensureFoundryConsent = useCallback(async (): Promise<void> => {
    if (IS_DEV_MODE || !account) return;
    try {
      // Already consented (e.g. a prior deploy)? Gate on the AGENT scope — it's the
      // one that actually blocks agent creation, and it's granted together with
      // Search in the popup below, so a missing agent scope must re-trigger consent.
      await msalInstance.acquireTokenSilent({ scopes: agentScopes, account });
      return;
    } catch {
      // One interactive consent: Search (primary token) + Foundry Agent
      // (extraScopesToConsent) so both can subsequently be acquired silently.
      await msalInstance.acquireTokenPopup({
        scopes: searchScopes,
        extraScopesToConsent: agentScopes,
      });
    }
  }, [account]);

  return (
    <AuthContext.Provider
      value={{ initialized, account, authError, login, logout, getFabricToken, getStorageToken, getManagementToken, getSearchToken, getAgentToken, getKustoToken, ensureFoundryConsent }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}

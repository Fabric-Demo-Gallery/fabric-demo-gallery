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
import { msalInstance, fabricScopes, storageScopes } from "@/lib/msal";

interface AuthState {
  initialized: boolean;
  account: AccountInfo | null;
  authError: string;
  login: () => Promise<void>;
  logout: () => void;
  getFabricToken: () => Promise<string>;
  getStorageToken: () => Promise<string>;
}

const AuthContext = createContext<AuthState>({
  initialized: false,
  account: null,
  authError: "",
  login: async () => {},
  logout: () => {},
  getFabricToken: async () => "",
  getStorageToken: async () => "",
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [initialized, setInitialized] = useState(false);
  const [account, setAccount] = useState<AccountInfo | null>(null);
  const [authError, setAuthError] = useState<string>("");

  useEffect(() => {
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
    try {
      await msalInstance.loginRedirect({
        scopes: ["openid", "profile"],
        extraScopesToConsent: ["https://api.fabric.microsoft.com/.default"],
      });
    } catch (e) {
      console.error("Login failed:", e);
    }
  }, []);

  const logout = useCallback(() => {
    msalInstance.logoutRedirect();
    setAccount(null);
  }, []);

  const getToken = useCallback(
    async (scopes: string[]): Promise<string> => {
      if (!account) throw new Error("Not signed in");
      try {
        const result = await msalInstance.acquireTokenSilent({
          scopes,
          account,
        });
        return result.accessToken;
      } catch (e) {
        // Any failure (interaction required, timeout, etc.) → use popup
        try {
          const result = await msalInstance.acquireTokenPopup({ scopes });
          return result.accessToken;
        } catch (popupErr) {
          // If popup also fails, try redirect as last resort
          console.error("Token popup failed:", popupErr);
          await msalInstance.acquireTokenRedirect({ scopes });
          throw new Error("Redirecting for token...");
        }
      }
    },
    [account]
  );

  const getFabricToken = useCallback(
    () => getToken(fabricScopes),
    [getToken]
  );

  const getStorageToken = useCallback(
    () => getToken(storageScopes),
    [getToken]
  );

  return (
    <AuthContext.Provider
      value={{ initialized, account, authError, login, logout, getFabricToken, getStorageToken }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}

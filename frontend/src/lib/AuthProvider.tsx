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
  type AccountInfo,
} from "@azure/msal-browser";
import { msalInstance, fabricScopes, storageScopes } from "@/lib/msal";

interface AuthState {
  initialized: boolean;
  account: AccountInfo | null;
  login: () => Promise<void>;
  logout: () => void;
  getFabricToken: () => Promise<string>;
  getStorageToken: () => Promise<string>;
}

const AuthContext = createContext<AuthState>({
  initialized: false,
  account: null,
  login: async () => {},
  logout: () => {},
  getFabricToken: async () => "",
  getStorageToken: async () => "",
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [initialized, setInitialized] = useState(false);
  const [account, setAccount] = useState<AccountInfo | null>(null);

  useEffect(() => {
    msalInstance.initialize().then(async () => {
      // Handle popup redirect response (closes the popup properly)
      try {
        const response = await msalInstance.handleRedirectPromise();
        if (response?.account) {
          msalInstance.setActiveAccount(response.account);
          setAccount(response.account);
        }
      } catch (e) {
        console.error("Redirect handling failed:", e);
      }

      const accounts = msalInstance.getAllAccounts();
      if (accounts.length > 0) {
        msalInstance.setActiveAccount(accounts[0]);
        setAccount(accounts[0]);
      }
      setInitialized(true);
    });
  }, []);

  const login = useCallback(async () => {
    try {
      await msalInstance.loginRedirect({
        scopes: fabricScopes,
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
        if (e instanceof InteractionRequiredAuthError) {
          const result = await msalInstance.acquireTokenPopup({ scopes });
          return result.accessToken;
        }
        throw e;
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
      value={{ initialized, account, login, logout, getFabricToken, getStorageToken }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  FluentProvider,
  webDarkTheme,
  Button,
  Avatar,
  Text,
  makeStyles,
} from "@fluentui/react-components";

const fabricFont = "'Segoe UI Variable Text', 'Segoe UI Variable', 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif";
const fabricTheme = {
  ...webDarkTheme,
  fontFamilyBase: fabricFont,
  fontFamilyMonospace: "'Cascadia Code', 'Consolas', monospace",
  fontFamilyNumeric: fabricFont,
};

import {
  PersonRegular,
  SignOutRegular,
  OpenRegular,
} from "@fluentui/react-icons";
import { AuthProvider } from "@/lib/AuthProvider";
import { useAuth } from "@/lib/AuthProvider";
import type { ReactNode } from "react";

/* Microsoft Fabric "F" ribbon logo */
function FabricLogo({ size = 20 }: { size?: number }) {
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img src="/fabric-logo.png" alt="Microsoft Fabric" width={size} height={size} style={{ objectFit: "contain" }} />
  );
}

const useStyles = makeStyles({
  topBar: {
    position: "sticky",
    top: 0,
    zIndex: 50,
    backgroundColor: "#010409",
    height: "48px",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    paddingLeft: "24px",
    paddingRight: "24px",
    borderBottom: "1px solid #21262d",
  },
  leftGroup: {
    display: "flex",
    alignItems: "center",
    gap: "16px",
  },
  brandLink: {
    display: "flex",
    alignItems: "center",
    gap: "10px",
    textDecoration: "none",
    color: "#e6edf3",
    fontSize: "14px",
    fontWeight: 600,
    ":hover": { textDecoration: "none", color: "#ffffff" },
  },
  separator: {
    width: "1px",
    height: "20px",
    backgroundColor: "#30363d",
  },
  navLink: {
    textDecoration: "none",
    color: "#8b949e",
    fontSize: "13px",
    fontWeight: 500,
    paddingTop: "4px",
    paddingBottom: "4px",
    paddingLeft: "8px",
    paddingRight: "8px",
    borderRadius: "6px",
    ":hover": {
      color: "#e6edf3",
      backgroundColor: "#21262d",
      textDecoration: "none",
    },
  },
  rightGroup: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
  },
  userName: {
    color: "#8b949e",
    fontSize: "13px",
  },
  main: {
    minHeight: "calc(100vh - 48px)",
    backgroundColor: "#0d1117",
  },
  footer: {
    backgroundColor: "#010409",
    borderTop: "1px solid #21262d",
    paddingTop: "24px",
    paddingBottom: "24px",
    textAlign: "center" as const,
  },
});

function Navbar() {
  const { account, login, logout, initialized } = useAuth();
  const styles = useStyles();

  return (
    <header className={styles.topBar}>
      <div className={styles.leftGroup}>
        <Link href="/" className={styles.brandLink}>
          <FabricLogo size={22} />
          Demo Gallery
        </Link>
        <div className={styles.separator} />
        <Link href="/" className={styles.navLink}>Demos</Link>
        <a
          href="https://github.com/microsoft/skills-for-fabric"
          target="_blank"
          rel="noopener noreferrer"
          className={styles.navLink}
        >
          GitHub <OpenRegular fontSize={11} style={{ marginLeft: 3, verticalAlign: "middle" }} />
        </a>
      </div>
      <div className={styles.rightGroup}>
        {initialized && (
          account ? (
            <>
              <Avatar
                name={account.username || "User"}
                size={28}
                color="colorful"
              />
              <span className={styles.userName}>{account.username}</span>
              <Button
                appearance="subtle"
                size="small"
                icon={<SignOutRegular />}
                onClick={logout}
                style={{ color: "#8b949e" }}
              >
                Sign out
              </Button>
            </>
          ) : (
            <Button
              size="small"
              icon={<PersonRegular />}
              onClick={login}
              style={{
                backgroundColor: "#238636",
                color: "#ffffff",
                border: "1px solid rgba(240,246,252,0.1)",
                borderRadius: "6px",
              }}
            >
              Sign in
            </Button>
          )
        )}
      </div>
    </header>
  );
}

export default function ClientShell({ children }: { children: ReactNode }) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  if (!mounted) {
    return (
      <div style={{ backgroundColor: "#0d1117", minHeight: "100vh" }}>
        <div style={{ backgroundColor: "#010409", height: 48, borderBottom: "1px solid #21262d" }} />
      </div>
    );
  }

  return <ClientShellInner>{children}</ClientShellInner>;
}

function ClientShellInner({ children }: { children: ReactNode }) {
  const styles = useStyles();
  return (
    <FluentProvider theme={fabricTheme}>
      <AuthProvider>
        <Navbar />
        <main className={styles.main}>{children}</main>
        <footer className={styles.footer}>
          <Text size={200} style={{ color: "#484f58" }}>
            Built with Microsoft Fabric REST APIs
          </Text>
        </footer>
      </AuthProvider>
    </FluentProvider>
  );
}

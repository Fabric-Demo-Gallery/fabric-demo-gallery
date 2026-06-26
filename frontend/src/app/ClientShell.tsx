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
  ShieldKeyholeRegular,
  ChevronDownRegular,
  DismissRegular,
} from "@fluentui/react-icons";
import { AuthProvider } from "@/lib/AuthProvider";
import { useAuth } from "@/lib/AuthProvider";
import { DeploymentProvider } from "@/lib/DeploymentContext";
import { BrowserUtils } from "@azure/msal-browser";
import NextLink from "next/link";
import { usePathname } from "next/navigation";
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
  const pathname = usePathname();

  return (
    <header className={styles.topBar}>
      <div className={styles.leftGroup}>
        <NextLink href="/" className={styles.brandLink}>
          <FabricLogo size={22} />
          Demo Gallery
        </NextLink>
        <div className={styles.separator} />
        <NextLink
          href="/"
          className={styles.navLink}
          aria-current={pathname === "/" ? "page" : undefined}
          style={pathname === "/" ? { color: "#e6edf3" } : undefined}
        >
          Demos
        </NextLink>
        {account && (
          <NextLink
            href="/monitoring"
            className={styles.navLink}
            aria-current={pathname === "/monitoring" ? "page" : undefined}
            style={pathname === "/monitoring" ? { color: "#e6edf3" } : undefined}
          >
            Monitoring
          </NextLink>
        )}
        <a
          href="https://github.com/Fabric-Demo-Gallery/fabric-demo-gallery"
          target="_blank"
          rel="noopener noreferrer"
          className={styles.navLink}
          aria-label="GitHub repository (opens in a new tab)"
        >
          GitHub <OpenRegular fontSize={11} aria-hidden style={{ marginLeft: 3, verticalAlign: "middle" }} />
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

const useNoteStyles = makeStyles({
  bar: {
    background: "linear-gradient(180deg, #0f1f3d 0%, #0d1a33 100%)",
    borderBottom: "1px solid rgba(56,139,253,0.3)",
  },
  inner: {
    maxWidth: "1080px",
    margin: "0 auto",
    display: "flex",
    alignItems: "flex-start",
    columnGap: "12px",
    paddingTop: "12px",
    paddingBottom: "12px",
    paddingLeft: "24px",
    paddingRight: "24px",
  },
  iconWrap: {
    flexShrink: 0,
    width: "30px",
    height: "30px",
    borderRadius: "8px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "rgba(56,139,253,0.15)",
    color: "#58a6ff",
    marginTop: "1px",
  },
  content: { flexGrow: 1, minWidth: 0, fontSize: "12.5px", lineHeight: "1.5", color: "#b6c2cf" },
  title: { fontWeight: 600, color: "#e6edf3", fontSize: "13px" },
  sub: { marginTop: "2px" },
  toggle: {
    backgroundColor: "transparent",
    border: "none",
    padding: "0",
    color: "#58a6ff",
    cursor: "pointer",
    fontWeight: 600,
    fontSize: "12.5px",
    display: "inline-flex",
    alignItems: "center",
    columnGap: "2px",
    ":hover": { textDecorationLine: "underline" },
  },
  chevron: { transitionProperty: "transform", transitionDuration: "0.15s" },
  details: {
    marginTop: "10px",
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
    gap: "10px",
  },
  method: {
    backgroundColor: "rgba(56,139,253,0.07)",
    border: "1px solid rgba(56,139,253,0.18)",
    borderRadius: "8px",
    paddingTop: "9px",
    paddingBottom: "9px",
    paddingLeft: "11px",
    paddingRight: "11px",
  },
  methodTitle: { fontWeight: 600, color: "#e6edf3", marginBottom: "3px", fontSize: "12px" },
  dismiss: {
    flexShrink: 0,
    backgroundColor: "transparent",
    border: "none",
    color: "#8b949e",
    cursor: "pointer",
    display: "flex",
    padding: "2px",
    borderRadius: "4px",
    ":hover": { color: "#e6edf3", backgroundColor: "rgba(255,255,255,0.06)" },
  },
});

function AdminConsentNote() {
  const { account } = useAuth();
  const s = useNoteStyles();
  const [dismissed, setDismissed] = useState(false);
  const [expanded, setExpanded] = useState(false);
  useEffect(() => {
    setDismissed(typeof window !== "undefined" && localStorage.getItem("fdg_admin_consent_note") === "dismissed");
  }, []);
  if (account || dismissed) return null;
  return (
    <div className={s.bar}>
      <div className={s.inner}>
        <span className={s.iconWrap}><ShieldKeyholeRegular fontSize={18} /></span>
        <div className={s.content}>
          <div className={s.title}>First time signing in from your organization?</div>
          <div className={s.sub}>
            If you hit <strong>&ldquo;Need admin approval&rdquo;</strong>, a one&#8209;time admin consent unblocks your whole tenant.{" "}
            <button className={s.toggle} onClick={() => setExpanded((v) => !v)}>
              {expanded ? "Hide steps" : "How to approve"}
              <ChevronDownRegular fontSize={14} className={s.chevron} style={{ transform: expanded ? "rotate(180deg)" : "none" }} />
            </button>
          </div>
          {expanded && (
            <div className={s.details}>
              <div className={s.method}>
                <div className={s.methodTitle}>You have an admin account</div>
                On the approval screen pick <strong>&ldquo;Have an admin account? Sign in with that account&rdquo;</strong>, sign in as a <strong>Global Administrator</strong>, and click <strong>Accept</strong>.
              </div>
              <div className={s.method}>
                <div className={s.methodTitle}>You can self&#8209;elevate (sandbox tenant)</div>
                <strong>Azure portal</strong> &rarr; search <strong>Privileged Identity Management</strong> &rarr; <strong>My roles</strong> &rarr; <strong>Activate</strong> the <strong>Global Administrator</strong> role (just&#8209;in&#8209;time), then approve.
              </div>
            </div>
          )}
        </div>
        <button
          className={s.dismiss}
          onClick={() => { localStorage.setItem("fdg_admin_consent_note", "dismissed"); setDismissed(true); }}
          aria-label="Dismiss"
        >
          <DismissRegular fontSize={16} />
        </button>
      </div>
    </div>
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

  // If this document is the MSAL sign-in/consent popup (or a hidden auth iframe) —
  // i.e. the redirect target after auth — do NOT mount the app here. The window that
  // opened the popup owns the handshake: it reads the auth response off this popup's
  // URL and closes it. Mounting the SPA (a second MSAL instance) in the popup consumes
  // that response first and strands the popup on the homepage (the bug we saw).
  if (BrowserUtils.isInPopup() || BrowserUtils.isInIframe()) {
    return (
      <div
        style={{
          backgroundColor: "#0d1117",
          color: "#8b949e",
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: fabricFont,
          fontSize: 14,
        }}
      >
        Completing sign-in…
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
        <DeploymentProvider>
        <Navbar />
        <AdminConsentNote />
        <main className={styles.main}>{children}</main>
        <footer className={styles.footer}>
          <Text size={200} style={{ color: "#484f58" }}>
            Built with Microsoft Fabric REST APIs
          </Text>
        </footer>
      </DeploymentProvider>
      </AuthProvider>
    </FluentProvider>
  );
}

"use client";

// Admin-consent guidance, shown next to the sign-in action (demo deploy panel,
// monitoring page). Lived as a global top-of-page banner until 2026-07-30; it
// only matters at the sign-in moment, so it now renders where that happens.
import { useEffect, useState } from "react";
import { makeStyles } from "@fluentui/react-components";
import { ShieldKeyholeRegular, ChevronDownRegular, DismissRegular } from "@fluentui/react-icons";
import { useAuth } from "@/lib/AuthProvider";

const useStyles = makeStyles({
  card: {
    display: "flex",
    alignItems: "flex-start",
    columnGap: "10px",
    backgroundColor: "rgba(56,139,253,0.06)",
    border: "1px solid rgba(56,139,253,0.25)",
    borderRadius: "8px",
    paddingTop: "10px",
    paddingBottom: "10px",
    paddingLeft: "11px",
    paddingRight: "8px",
    marginTop: "10px",
  },
  iconWrap: {
    flexShrink: 0,
    width: "26px",
    height: "26px",
    borderRadius: "6px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "rgba(56,139,253,0.15)",
    color: "#58a6ff",
    marginTop: "1px",
  },
  content: { flexGrow: 1, minWidth: 0, fontSize: "12px", lineHeight: "1.5", color: "#b6c2cf" },
  title: { fontWeight: 600, color: "#e6edf3", fontSize: "12.5px" },
  sub: { marginTop: "2px" },
  toggle: {
    backgroundColor: "transparent",
    border: "none",
    padding: "0",
    color: "#58a6ff",
    cursor: "pointer",
    fontWeight: 600,
    fontSize: "12px",
    display: "inline-flex",
    alignItems: "center",
    columnGap: "2px",
    ":hover": { textDecorationLine: "underline" },
  },
  chevron: { transitionProperty: "transform", transitionDuration: "0.15s" },
  details: {
    marginTop: "8px",
    display: "flex",
    flexDirection: "column",
    rowGap: "8px",
  },
  method: {
    backgroundColor: "rgba(56,139,253,0.07)",
    border: "1px solid rgba(56,139,253,0.18)",
    borderRadius: "8px",
    paddingTop: "8px",
    paddingBottom: "8px",
    paddingLeft: "10px",
    paddingRight: "10px",
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

export default function AdminConsentNote({ variant = "card" }: { variant?: "card" | "hover" }) {
  const { account } = useAuth();
  const s = useStyles();
  const isHover = variant === "hover";
  const [dismissed, setDismissed] = useState(false);
  const [expanded, setExpanded] = useState(false);
  // mounted gate: keep this sign-in guidance OUT of the prerendered HTML - it was
  // once scraped as the search snippet (Bing ignores data-nosnippet). Server and
  // first client render both return null, so hydration stays consistent.
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
    setDismissed(typeof window !== "undefined" && localStorage.getItem("fdg_admin_consent_note") === "dismissed");
  }, []);
  // Hover variant lives inside a popover surface that only mounts client-side on
  // open, so the prerender/dismissal gates don't apply and steps show directly.
  if (account) return null;
  if (!isHover && (!mounted || dismissed)) return null;
  const showSteps = isHover || expanded;
  return (
    // data-nosnippet: tells Google not to use this guidance as the search
    // snippet (it's sign-in help, not page content).
    <div
      className={s.card}
      style={isHover ? { marginTop: 0, backgroundColor: "transparent", border: "none", padding: 0 } : undefined}
      data-nosnippet=""
    >
      <span className={s.iconWrap}><ShieldKeyholeRegular fontSize={16} /></span>
      <div className={s.content}>
        <div className={s.title}>First time signing in from your organization?</div>
        <div className={s.sub}>
          If you hit <strong>&ldquo;Need admin approval&rdquo;</strong>, a one&#8209;time admin consent unblocks your whole tenant.{" "}
          {!isHover && (
            <button className={s.toggle} onClick={() => setExpanded((v) => !v)}>
              {expanded ? "Hide steps" : "How to approve"}
              <ChevronDownRegular fontSize={13} className={s.chevron} style={{ transform: expanded ? "rotate(180deg)" : "none" }} />
            </button>
          )}
        </div>
        {showSteps && (
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
      {!isHover && (
        <button
          className={s.dismiss}
          onClick={() => { localStorage.setItem("fdg_admin_consent_note", "dismissed"); setDismissed(true); }}
          aria-label="Dismiss"
        >
          <DismissRegular fontSize={14} />
        </button>
      )}
    </div>
  );
}

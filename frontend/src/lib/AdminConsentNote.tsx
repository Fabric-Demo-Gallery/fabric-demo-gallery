"use client";

import { useEffect, useId, useState } from "react";
import { makeStyles } from "@fluentui/react-components";
import { ShieldKeyholeRegular, ChevronDownRegular } from "@fluentui/react-icons";
import { useAuth } from "@/lib/AuthProvider";

const useStyles = makeStyles({
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
    "@media (max-width: 640px)": {
      paddingLeft: "12px",
      paddingRight: "12px",
    },
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
    fontSize: "12px",
    display: "inline-flex",
    alignItems: "center",
    columnGap: "2px",
    ":hover": { textDecorationLine: "underline" },
  },
  chevron: { transitionProperty: "transform", transitionDuration: "0.15s" },
  details: {
    marginTop: "10px",
    display: "grid",
    gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
    gap: "10px",
    "@media (max-width: 640px)": {
      gridTemplateColumns: "minmax(0, 1fr)",
    },
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
});

export default function AdminConsentNote() {
  const { account, initialized } = useAuth();
  const s = useStyles();
  const detailsId = useId();
  const [expanded, setExpanded] = useState(false);
  // mounted gate: keep this sign-in guidance OUT of the prerendered HTML - it was
  // once scraped as the search snippet (Bing ignores data-nosnippet). Server and
  // first client render both return null, so hydration stays consistent.
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);
  if (!mounted || !initialized || account) return null;
  return (
    // data-nosnippet: tells Google not to use this guidance as the search
    // snippet (it's sign-in help, not page content).
    <aside className={s.bar} aria-label="Sign-in admin consent guidance" data-nosnippet="">
      <div className={s.inner}>
        <span className={s.iconWrap}><ShieldKeyholeRegular fontSize={16} aria-hidden /></span>
        <div className={s.content}>
          <div className={s.title}>First time signing in from your organization?</div>
          <div className={s.sub}>
            If you see <strong>&ldquo;Need admin approval&rdquo;</strong>, ask a <strong>Global Administrator</strong> to sign in and grant one&#8209;time consent for your organization.{" "}
            <button
              type="button"
              className={s.toggle}
              aria-expanded={expanded}
              aria-controls={detailsId}
              onClick={() => setExpanded((v) => !v)}
            >
              {expanded ? "Hide steps" : "How to approve"}
              <ChevronDownRegular fontSize={13} aria-hidden className={s.chevron} style={{ transform: expanded ? "rotate(180deg)" : "none" }} />
            </button>
          </div>
          <div id={detailsId} hidden={!expanded}>
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
          </div>
        </div>
      </div>
    </aside>
  );
}

"use client";

import { useState } from "react";
import { ToggleButton, makeStyles } from "@fluentui/react-components";
import NextLink from "next/link";
import { industries } from "@/lib/industryCatalog";

const FEATURE_FILTERS = [
  "RTI",
  "Fabric IQ",
  "Fabric Data Agents",
  "Power BI",
  "Machine Learning",
  "Shortcuts & Mirroring",
];

const useStyles = makeStyles({
  /* ---- Hero ---- */
  hero: {
    background: "#0d1117",
    color: "#e6edf3",
    borderBottom: "1px solid #21262d",
  },
  heroInner: {
    maxWidth: "1200px",
    marginLeft: "auto",
    marginRight: "auto",
    paddingLeft: "40px",
    paddingRight: "40px",
    paddingTop: "48px",
    paddingBottom: "48px",
  },
  heroEyebrow: {
    display: "inline-flex",
    alignItems: "center",
    gap: "8px",
    fontSize: "12px",
    fontWeight: 600,
    textTransform: "uppercase" as const,
    letterSpacing: "1.5px",
    color: "#3fb68b",
    marginBottom: "12px",
  },
  heroTitle: {
    fontSize: "32px",
    fontWeight: 700,
    lineHeight: "40px",
    maxWidth: "560px",
    marginBottom: "12px",
    color: "#e6edf3",
  },
  heroDesc: {
    fontSize: "15px",
    lineHeight: "22px",
    maxWidth: "520px",
    color: "#8b949e",
  },

  /* ---- Content ---- */
  content: {
    maxWidth: "1200px",
    marginLeft: "auto",
    marginRight: "auto",
    paddingLeft: "40px",
    paddingRight: "40px",
    paddingTop: "32px",
    paddingBottom: "48px",
  },
  /* ---- Cards ---- */
  cardGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fill, minmax(480px, 1fr))",
    gap: "16px",
    marginBottom: "40px",
  },
  card: {
    cursor: "pointer",
    backgroundColor: "#161b22",
    border: "1px solid #30363d",
    borderRadius: "8px",
    overflow: "hidden",
    transitionProperty: "box-shadow",
    transitionDuration: "0.15s",
    ":hover": {
      boxShadow: "0 0 0 1px #3fb68b, 0 4px 12px rgba(0,0,0,0.3)",
    },
  },
  cardAccent: {
    height: "2px",
    backgroundColor: "#3fb68b",
  },
  cardBody: {
    padding: "20px 24px 24px",
  },
  cardHeader: {
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    marginBottom: "12px",
  },
  cardHeaderLeft: {
    display: "flex",
    alignItems: "center",
    gap: "12px",
  },
  cardIcon: {
    width: "40px",
    height: "40px",
    borderRadius: "8px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#21262d",
    flexShrink: 0,
  },
  cardTitleGroup: {},
  cardTitle: {
    fontSize: "16px",
    fontWeight: 600,
    color: "#e6edf3",
    lineHeight: "22px",
    marginBottom: "2px",
  },
  cardDesc: {
    fontSize: "14px",
    color: "#8b949e",
    lineHeight: "22px",
    marginBottom: "16px",
  },
});

export default function Home() {
  const styles = useStyles();
  const [featureFilter, setFeatureFilter] = useState("All");

  const filtered = industries.filter((ind) => {
    if (!ind.enabled) return false;
    if (featureFilter === "All") return true;
    return ind.features?.includes(featureFilter) ?? false;
  });

  return (
    <>
      {/* Hero */}
      <div className={styles.hero}>
        <div className={styles.heroInner}>
          <div className={styles.heroEyebrow}>Microsoft Fabric</div>
          <div className={styles.heroTitle}>Industry Demo Gallery</div>
          <div className={styles.heroDesc}>
            Explore and deploy analytics solutions for your industry. Start by
            choosing an industry below, then select a use case and deployment
            type. Easily extendable for future industries and scenarios.
          </div>
        </div>
      </div>

      {/* Content */}
      <div className={styles.content}>
        {/* Feature filters */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 20 }}>
          {["All", ...FEATURE_FILTERS].map((feat) => (
            <ToggleButton
              key={feat}
              size="small"
              appearance={featureFilter === feat ? "primary" : "subtle"}
              checked={featureFilter === feat}
              onClick={() => setFeatureFilter(feat)}
            >
              {feat}
            </ToggleButton>
          ))}
        </div>

        {/* Industry Cards */}
        <div className={styles.cardGrid}>
          {filtered.length === 0 && (
            <div style={{ gridColumn: "1 / -1", textAlign: "center", padding: "48px 0", color: "#484f58" }}>
              No industries match the selected feature.
            </div>
          )}
          {filtered.map((industry) => (
            <NextLink
              key={industry.slug}
              href={`/industries/${industry.slug}`}
              style={{ textDecoration: "none" }}
            >
              <div className={styles.card}>
                <div className={styles.cardAccent} />
                <div className={styles.cardBody}>
                  <div className={styles.cardHeader}>
                    <div className={styles.cardHeaderLeft}>
                      <div className={styles.cardIcon}>
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img
                          src={industry.icon.startsWith("/") ? industry.icon : `/icons/${industry.icon}`}
                          alt=""
                          width={32}
                          height={32}
                          style={{ objectFit: "contain" }}
                        />
                      </div>
                      <div className={styles.cardTitleGroup}>
                        <div className={styles.cardTitle}>{industry.title}</div>
                      </div>
                    </div>
                  </div>
                  <div className={styles.cardDesc}>{industry.description}</div>
                </div>
              </div>
            </NextLink>
          ))}
        </div>
      </div>
    </>
  );
}

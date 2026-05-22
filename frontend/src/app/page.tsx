"use client";

import NextLink from "next/link";
import { makeStyles } from "@fluentui/react-components";
import { industries } from "@/lib/industryCatalog";

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
  heroStats: {
    display: "flex",
    gap: "40px",
    marginTop: "32px",
  },
  heroStat: {},
  heroStatNum: {
    fontSize: "32px",
    fontWeight: 700,
    color: "#3fb68b",
    lineHeight: "36px",
  },
  heroStatLabel: {
    fontSize: "12px",
    color: "#484f58",
    marginTop: "4px",
    textTransform: "uppercase" as const,
    letterSpacing: "0.5px",
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
  toolbar: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: "20px",
  },
  sectionLabel: {
    fontSize: "16px",
    fontWeight: 600,
    color: "#e6edf3",
  },
  filterBar: {
    display: "flex",
    gap: "4px",
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
  cardIndustry: {
    fontSize: "12px",
    color: "#8b949e",
    fontWeight: 500,
  },
  cardArrow: {
    color: "#484f58",
    flexShrink: 0,
    marginTop: "4px",
  },
  cardDesc: {
    fontSize: "14px",
    color: "#8b949e",
    lineHeight: "22px",
    marginBottom: "16px",
  },
  cardFooter: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
  },
  cardMeta: {
    display: "flex",
    alignItems: "center",
    gap: "16px",
  },
  metaItem: {
    display: "flex",
    alignItems: "center",
    gap: "4px",
    fontSize: "12px",
    color: "#484f58",
  },
  tagRow: {
    display: "flex",
    flexWrap: "wrap" as const,
    gap: "4px",
  },

  /* ---- Items strip ---- */
  itemStrip: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    paddingTop: "12px",
    marginTop: "12px",
    borderTop: "1px solid #21262d",
  },
  itemStripLabel: {
    fontSize: "11px",
    color: "#484f58",
    fontWeight: 500,
    textTransform: "uppercase" as const,
    letterSpacing: "0.5px",
    marginRight: "4px",
  },
  itemStripIcon: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    width: "26px",
    height: "26px",
    borderRadius: "6px",
    backgroundColor: "#21262d",
    border: "1px solid #30363d",
  },

  /* ---- How it works ---- */
  howSection: {
    marginBottom: "40px",
  },
  howTitle: {
    fontSize: "16px",
    fontWeight: 600,
    color: "#e6edf3",
    marginBottom: "16px",
  },
  stepsRow: {
    display: "grid",
    gridTemplateColumns: "repeat(4, 1fr)",
    gap: "12px",
  },
  stepCard: {
    backgroundColor: "#161b22",
    border: "1px solid #30363d",
    borderRadius: "8px",
    padding: "24px 16px",
    textAlign: "center" as const,
  },
  stepNum: {
    width: "32px",
    height: "32px",
    borderRadius: "50%",
    color: "#ffffff",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: "14px",
    fontWeight: 700,
    marginLeft: "auto",
    marginRight: "auto",
    marginBottom: "12px",
  },
  stepTitle: {
    fontSize: "14px",
    fontWeight: 600,
    color: "#e6edf3",
    marginBottom: "4px",
  },
  stepDesc: {
    fontSize: "12px",
    color: "#8b949e",
    lineHeight: "16px",
  },
});

const STEP_COLORS = ["#3fb68b", "#2da882", "#1a9b80", "#117865"];

const STEPS = [
  { n: 1, t: "Browse", d: "Choose an industry demo" },
  { n: 2, t: "Authenticate", d: "Sign in with Microsoft Entra" },
  { n: 3, t: "Configure", d: "Name workspace & pick capacity" },
  { n: 4, t: "Deploy", d: "Watch real-time provisioning" },
];

/* Fabric workload icons — official SVGs from Microsoft */
function FabricItemIcon({ type, size = 14 }: { type: string; size?: number }) {
  const FILE_MAP: Record<string, string> = {
    Lakehouse: "lakehouse_24_item.svg",
    Notebook: "notebook_24_item.svg",
    SemanticModel: "semantic_model_24_item.svg",
    Report: "report_24_item.svg",
    DataPipeline: "pipeline_24_item.svg",
    Dashboard: "dashboard_24_item.svg",
    Eventhouse: "eventhouse_24_item.svg",
    KQLDatabase: "kql_database_24_item.svg",
    KQLDashboard: "kql_dashboard_24_item.svg",
  };
  const file = FILE_MAP[type];
  if (!file) return null;
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={`/icons/${file}`} alt={type} width={size} height={size} style={{ objectFit: "contain" }} />;
}

const ITEM_TYPES = ["Lakehouse", "Notebook", "SemanticModel", "Report", "DataPipeline", "Eventhouse", "KQLDatabase", "KQLDashboard"];

export default function Home() {
  const styles = useStyles();

  return (
    <>
      {/* Hero */}
      <div className={styles.hero}>
        <div className={styles.heroInner}>
          <div className={styles.heroEyebrow}>Microsoft Fabric</div>
          <div className={styles.heroTitle}>Industry Demo Gallery</div>
          <div className={styles.heroDesc}>
            Explore and deploy analytics solutions for your industry. Start by choosing an industry below, then select a use case and deployment type. Easily extendable for future industries and scenarios.
          </div>
        </div>
      </div>

      {/* Content: Industry Tiles */}
      <div className={styles.content}>
        <div className={styles.cardGrid}>
          {industries.filter((ind) => ind.enabled).map((industry) => (
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
                        <img src={industry.icon.startsWith("/") ? industry.icon : `/icons/${industry.icon}`} alt="" width={32} height={32} style={{ objectFit: "contain" }} />
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

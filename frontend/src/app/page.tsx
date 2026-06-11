"use client";


import Link from "next/link";
import { useMemo, useState } from "react";
import { makeStyles } from "@fluentui/react-components";
import {
  BuildingFactory24Regular,
  BuildingRetail24Regular,
  Flash24Regular,
  BuildingBank24Regular,
  Briefcase24Regular,
  HeartPulse24Regular,
  Laptop24Regular,
  VehicleTruck24Regular,
  BuildingMultiple24Regular,
  Video24Regular,
  HatGraduation24Regular,
  Bed24Regular,
} from "@fluentui/react-icons";
import type { FluentIcon } from "@fluentui/react-icons";
import { industries } from "@/lib/industryCatalog";
import { DEMOS } from "@/lib/demoCatalog";

// Professional Fluent System icons per industry (replaces hand-drawn SVGs).
const INDUSTRY_ICON: Record<string, FluentIcon> = {
  manufacturing: BuildingFactory24Regular,
  retail: BuildingRetail24Regular,
  energy: Flash24Regular,
  "financial-services": BuildingBank24Regular,
  "professional-services": Briefcase24Regular,
  healthcare: HeartPulse24Regular,
  technology: Laptop24Regular,
  transportation: VehicleTruck24Regular,
  construction: BuildingMultiple24Regular,
  media: Video24Regular,
  education: HatGraduation24Regular,
  hospitality: Bed24Regular,
};

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

  /* ---- Search + filters ---- */
  controls: {
    display: "flex",
    flexDirection: "column" as const,
    gap: "14px",
    marginBottom: "24px",
  },
  searchRow: {
    position: "relative" as const,
    maxWidth: "520px",
  },
  searchInput: {
    width: "100%",
    boxSizing: "border-box" as const,
    backgroundColor: "#0d1117",
    border: "1px solid #30363d",
    borderRadius: "8px",
    color: "#e6edf3",
    fontSize: "14px",
    padding: "10px 14px 10px 38px",
    outline: "none",
    ":focus": {
      borderTopColor: "#3fb68b",
      borderRightColor: "#3fb68b",
      borderBottomColor: "#3fb68b",
      borderLeftColor: "#3fb68b",
    },
    "::placeholder": { color: "#484f58" },
  },
  searchIcon: {
    position: "absolute" as const,
    left: "12px",
    top: "50%",
    transform: "translateY(-50%)",
    color: "#484f58",
    pointerEvents: "none" as const,
  },
  filterGroup: {
    display: "flex",
    flexWrap: "wrap" as const,
    alignItems: "center",
    gap: "6px",
  },
  filterGroupLabel: {
    fontSize: "11px",
    fontWeight: 600,
    color: "#484f58",
    textTransform: "uppercase" as const,
    letterSpacing: "0.5px",
    marginRight: "4px",
  },
  chip: {
    display: "inline-flex",
    alignItems: "center",
    gap: "6px",
    cursor: "pointer",
    backgroundColor: "#161b22",
    border: "1px solid #30363d",
    borderRadius: "16px",
    color: "#8b949e",
    fontSize: "12px",
    fontWeight: 500,
    padding: "5px 12px",
    transitionProperty: "all",
    transitionDuration: "0.12s",
    ":hover": {
      borderTopColor: "#3fb68b",
      borderRightColor: "#3fb68b",
      borderBottomColor: "#3fb68b",
      borderLeftColor: "#3fb68b",
      color: "#e6edf3",
    },
  },
  chipActive: {
    backgroundColor: "#132f27",
    borderTopColor: "#3fb68b",
    borderRightColor: "#3fb68b",
    borderBottomColor: "#3fb68b",
    borderLeftColor: "#3fb68b",
    color: "#3fb68b",
  },
  resultCount: {
    fontSize: "13px",
    color: "#8b949e",
    marginBottom: "12px",
  },
  noResults: {
    textAlign: "center" as const,
    padding: "48px 0",
    color: "#8b949e",
  },
  cardMetaRow: {
    display: "flex",
    alignItems: "center",
    gap: "12px",
    flexWrap: "wrap" as const,
    marginTop: "4px",
  },
  patternPill: {
    display: "inline-flex",
    alignItems: "center",
    fontSize: "11px",
    fontWeight: 600,
    color: "#3fb68b",
    backgroundColor: "#132f27",
    borderRadius: "4px",
    padding: "2px 8px",
    textTransform: "capitalize" as const,
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
  const [query, setQuery] = useState("");
  const [pattern, setPattern] = useState<string | null>(null);
  const [itemType, setItemType] = useState<string | null>(null);

  // Join each enabled industry with its mapped demo metadata.
  const cards = useMemo(
    () =>
      industries
        .filter((ind) => ind.enabled)
        .map((ind) => ({ ind, demo: ind.demoId ? DEMOS[ind.demoId] : undefined })),
    []
  );

  const patterns = useMemo(
    () =>
      Array.from(
        new Set(cards.map((c) => c.demo?.architecture.pattern).filter(Boolean))
      ) as string[],
    [cards]
  );

  const itemTypes = useMemo(
    () =>
      Array.from(
        new Set(cards.flatMap((c) => c.demo?.fabricItems.map((i) => i.type) ?? []))
      ).filter((t) => ITEM_TYPES.includes(t)).sort(),
    [cards]
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return cards.filter(({ ind, demo }) => {
      if (pattern && demo?.architecture.pattern !== pattern) return false;
      if (itemType && !demo?.fabricItems.some((i) => i.type === itemType)) return false;
      if (q) {
        const hay = [ind.title, ind.description, demo?.title, demo?.description, demo?.industry]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [cards, query, pattern, itemType]);

  const hasFilters = query.trim() !== "" || pattern !== null || itemType !== null;
  const clearAll = () => {
    setQuery("");
    setPattern(null);
    setItemType(null);
  };

  return (
    <>
      {/* Hero */}
      <div className={styles.hero}>
        <div className={styles.heroInner}>
          <div className={styles.heroEyebrow}>Microsoft Fabric</div>
          <div className={styles.heroTitle}>Industry Demo Gallery</div>
          <div className={styles.heroDesc}>
            Browse production-ready Fabric demos by industry. Filter by architecture or
            workload, then deploy a complete environment in minutes.
          </div>
        </div>
      </div>

      {/* Content */}
      <div className={styles.content}>
        {/* Search + filters */}
        <div className={styles.controls}>
          <div className={styles.searchRow}>
            <span className={styles.searchIcon}>
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                <path
                  d="M11.5 11.5L14 14M7 12.5a5.5 5.5 0 100-11 5.5 5.5 0 000 11z"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                />
              </svg>
            </span>
            <input
              className={styles.searchInput}
              type="text"
              placeholder="Search demos by industry, use case, or keyword…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              aria-label="Search demos"
            />
          </div>

          <div className={styles.filterGroup}>
            <span className={styles.filterGroupLabel}>Architecture</span>
            <button
              className={`${styles.chip} ${pattern === null ? styles.chipActive : ""}`}
              onClick={() => setPattern(null)}
            >
              All
            </button>
            {patterns.map((p) => (
              <button
                key={p}
                className={`${styles.chip} ${pattern === p ? styles.chipActive : ""}`}
                onClick={() => setPattern(pattern === p ? null : p)}
                style={{ textTransform: "capitalize" }}
              >
                {p}
              </button>
            ))}
          </div>

          <div className={styles.filterGroup}>
            <span className={styles.filterGroupLabel}>Fabric item</span>
            <button
              className={`${styles.chip} ${itemType === null ? styles.chipActive : ""}`}
              onClick={() => setItemType(null)}
            >
              All
            </button>
            {itemTypes.map((t) => (
              <button
                key={t}
                className={`${styles.chip} ${itemType === t ? styles.chipActive : ""}`}
                onClick={() => setItemType(itemType === t ? null : t)}
              >
                <FabricItemIcon type={t} size={14} />
                {t}
              </button>
            ))}
          </div>
        </div>

        {/* Result count */}
        <div className={styles.resultCount}>
          {filtered.length} {filtered.length === 1 ? "demo" : "demos"}
          {hasFilters && (
            <>
              {" · "}
              <button
                onClick={clearAll}
                style={{
                  background: "none",
                  border: "none",
                  color: "#3fb68b",
                  cursor: "pointer",
                  fontSize: "13px",
                  padding: 0,
                }}
              >
                Clear filters
              </button>
            </>
          )}
        </div>

        {/* Cards */}
        {filtered.length === 0 ? (
          <div className={styles.noResults}>
            No demos match your search. <br />
            <button
              onClick={clearAll}
              style={{
                background: "none",
                border: "none",
                color: "#3fb68b",
                cursor: "pointer",
                fontSize: "14px",
                marginTop: "8px",
              }}
            >
              Clear filters
            </button>
          </div>
        ) : (
          <div className={styles.cardGrid}>
            {filtered.map(({ ind, demo }) => {
              const items = demo?.fabricItems ?? [];
              const uniqueTypes = Array.from(new Set(items.map((i) => i.type)));
              return (
                <Link
                  key={ind.slug}
                  href={`/industries/${ind.slug}`}
                  style={{ textDecoration: "none" }}
                >
                  <div className={styles.card}>
                    <div className={styles.cardAccent} />
                    <div className={styles.cardBody}>
                      <div className={styles.cardHeader}>
                        <div className={styles.cardHeaderLeft}>
                          <div className={styles.cardIcon}>
                            {(() => {
                              const Icon = INDUSTRY_ICON[ind.slug] ?? BuildingMultiple24Regular;
                              return <Icon fontSize={24} color="#3fb68b" aria-hidden />;
                            })()}
                          </div>
                          <div className={styles.cardTitleGroup}>
                            <div className={styles.cardTitle}>{ind.title}</div>
                            {demo && <div className={styles.cardIndustry}>{demo.title}</div>}
                          </div>
                        </div>
                      </div>
                      <div className={styles.cardDesc}>{demo?.description ?? ind.description}</div>

                      {demo && (
                        <div className={styles.cardMetaRow}>
                          <span className={styles.patternPill}>{demo.architecture.pattern}</span>
                          <span className={styles.metaItem}>{demo.estimatedTime}</span>
                        </div>
                      )}

                      {uniqueTypes.length > 0 && (
                        <div className={styles.itemStrip}>
                          <span className={styles.itemStripLabel}>Includes</span>
                          {uniqueTypes.map((t) => (
                            <span key={t} className={styles.itemStripIcon} title={t}>
                              <FabricItemIcon type={t} size={16} />
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}

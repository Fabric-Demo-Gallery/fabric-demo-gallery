"use client";


import Link from "next/link";
import { useMemo } from "react";
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

// Self-hosted product demo video, served from /public (same-origin). This avoids
// YouTube's embed referrer/bot-check gates entirely — it just plays for everyone.
// Set to "" to hide the player and show a "coming soon" placeholder.
const DEMO_VIDEO_SRC = "/demo.mp4";

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

  /* ---- Hero video ---- */
  heroGrid: {
    display: "flex",
    alignItems: "center",
    gap: "48px",
    flexWrap: "wrap" as const,
  },
  heroCopy: {
    flex: "1 1 360px",
    minWidth: "280px",
  },
  heroVideoCol: {
    flex: "1 1 480px",
    minWidth: "280px",
  },
  heroVideoFrame: {
    position: "relative",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    width: "100%",
    aspectRatio: "16 / 9",
    borderRadius: "10px",
    overflow: "hidden",
    borderTop: "1px solid #30363d",
    borderRight: "1px solid #30363d",
    borderBottom: "1px solid #30363d",
    borderLeft: "1px solid #30363d",
    backgroundColor: "#161b22",
    backgroundSize: "cover",
    backgroundPosition: "center",
    padding: 0,
    margin: 0,
    appearance: "none" as const,
    fontFamily: "inherit",
    color: "inherit",
    textAlign: "center" as const,
  },
  heroVideoButton: {
    cursor: "pointer",
    transitionProperty: "box-shadow",
    transitionDuration: "0.15s",
    ":hover": {
      boxShadow: "0 0 0 1px #3fb68b, 0 6px 18px rgba(0,0,0,0.4)",
    },
  },
  heroVideoIframe: {
    position: "absolute",
    top: 0,
    left: 0,
    width: "100%",
    height: "100%",
    borderTop: "none",
    borderRight: "none",
    borderBottom: "none",
    borderLeft: "none",
  },
  heroVideoEl: {
    position: "absolute",
    top: 0,
    left: 0,
    width: "100%",
    height: "100%",
    objectFit: "cover" as const,
    backgroundColor: "#000000",
  },
  heroVideoOverlay: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundImage: "linear-gradient(180deg, rgba(13,17,23,0.15), rgba(13,17,23,0.6))",
  },
  heroVideoPlay: {
    position: "relative",
    display: "flex",
    color: "#ffffff",
    filter: "drop-shadow(0 2px 10px rgba(0,0,0,0.55))",
  },
  heroVideoCaption: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: "12px",
    textAlign: "center" as const,
    fontSize: "12px",
    fontWeight: 600,
    letterSpacing: "0.3px",
    color: "rgba(255,255,255,0.92)",
    textShadow: "0 1px 4px rgba(0,0,0,0.6)",
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

  /* ---- Misc ---- */
  cardMetaRow: {
    display: "flex",
    alignItems: "center",
    gap: "12px",
    flexWrap: "wrap" as const,
    marginTop: "4px",
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

// Hero product-demo video. Self-hosted native <video> — no third-party player,
// no embed/referrer/bot-check issues. preload="metadata" + the #t fragment shows
// a first-frame poster without downloading the whole file until the user plays.
function HeroVideo() {
  const styles = useStyles();
  const src = DEMO_VIDEO_SRC.trim();

  if (!src) {
    return (
      <div className={styles.heroVideoFrame}>
        <span className={styles.heroVideoOverlay} />
        <span className={styles.heroVideoCaption}>Demo video coming soon</span>
      </div>
    );
  }

  return (
    <div className={styles.heroVideoFrame}>
      <video
        className={styles.heroVideoEl}
        src={`${src}#t=0.1`}
        controls
        preload="metadata"
        playsInline
        title="Fabric Demo Gallery product demo"
      />
    </div>
  );
}

export default function Home() {
  const styles = useStyles();

  // Join each enabled industry with its mapped demo metadata.
  const cards = useMemo(
    () =>
      industries
        .filter((ind) => ind.enabled)
        .map((ind) => ({ ind, demo: ind.demoId ? DEMOS[ind.demoId] : undefined })),
    []
  );

  return (
    <>
      {/* Hero */}
      <div className={styles.hero}>
        <div className={styles.heroInner}>
          <div className={styles.heroGrid}>
            <div className={styles.heroCopy}>
              <div className={styles.heroEyebrow}>Microsoft Fabric</div>
              <h1 className={styles.heroTitle} style={{ margin: 0 }}>Industry Demo Gallery</h1>
              <div className={styles.heroDesc}>
                Browse production-ready Fabric demos by industry, then deploy a complete
                environment in minutes.
              </div>
            </div>
            <div className={styles.heroVideoCol}>
              <HeroVideo />
            </div>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className={styles.content}>
        {/* Cards */}
        <div className={styles.cardGrid}>
            {cards.map(({ ind, demo }) => {
              return (
                <Link
                  key={ind.slug}
                  href={`/industries/${ind.slug}`}
                  style={{ textDecoration: "none", display: "block" }}
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
                          <span className={styles.metaItem}>{demo.estimatedTime}</span>
                        </div>
                      )}
                    </div>
                  </div>
                </Link>
              );
            })}
        </div>
      </div>
    </>
  );
}

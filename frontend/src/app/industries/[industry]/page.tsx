import { notFound } from "next/navigation";
import Link from "next/link";
import type { ReactNode } from "react";
import { industries } from "@/lib/industryCatalog";
import { DEMOS } from "@/lib/demoCatalog";
import { Breadcrumbs } from "@/lib/Breadcrumbs";

// Mirror of the gallery's item-symbol renderer so the "Includes" strip looks
// identical on the industry page.
function FabricItemIcon({ type, size = 16 }: { type: string; size?: number }) {
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

const styles = {
  page: {
    minHeight: "100vh",
    backgroundColor: "#0d1117",
  },
  inner: {
    maxWidth: "900px",
    margin: "0 auto",
    padding: "40px 40px 48px 40px",
  },
  title: {
    fontSize: "28px",
    fontWeight: 700,
    color: "#e6edf3",
    marginBottom: "8px",
  },
  desc: {
    color: "#8b949e",
    marginBottom: "32px",
    fontSize: "15px",
  },
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
    gap: "24px",
  },
  card: {
    backgroundColor: "#161b22",
    border: "1px solid #30363d",
    borderRadius: "8px",
    padding: "28px 24px 24px 24px",
    display: "flex",
    flexDirection: "column",
    alignItems: "flex-start",
    minHeight: "140px",
    cursor: "pointer",
    transition: "box-shadow 0.15s",
  },
  cardTitle: {
    fontSize: "17px",
    fontWeight: 600,
    color: "#e6edf3",
    marginBottom: "8px",
  },
  cardDesc: {
    color: "#8b949e",
    fontSize: "14px",
    flexGrow: 1,
    marginBottom: "8px",
  },
  itemStrip: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    flexWrap: "wrap" as const,
    paddingTop: "14px",
    marginTop: "14px",
    borderTop: "1px solid #21262d",
    width: "100%",
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
} as const;

// A deployment option card. When there's no demo (coming soon) we render a
// NON-interactive div with aria-disabled instead of a <Link href="#">, so
// keyboard users can't tab to / activate a broken link (pointerEvents only
// blocks the mouse).
function DeployOption({ href, enabled, children }: { href: string; enabled: boolean; children: ReactNode }) {
  if (!enabled) {
    return (
      <div aria-disabled="true" style={{ textDecoration: "none", display: "block", opacity: 0.5, pointerEvents: "none" }}>
        {children}
      </div>
    );
  }
  return (
    <Link href={href} style={{ textDecoration: "none", display: "block" }}>
      {children}
    </Link>
  );
}

export function generateStaticParams() {
  return industries.filter((i) => i.enabled).map((i) => ({ industry: i.slug }));
}

export default async function IndustryPage({ params }: { params: Promise<{ industry: string }> }) {
  const { industry: industrySlug } = await params;
  const industry = industries.find((i) => i.slug === industrySlug && i.enabled);
  if (!industry) return notFound();

  const demo = industry.demoId ? DEMOS[industry.demoId] : undefined;
  const uniqueTypes = demo
    ? Array.from(new Set(demo.fabricItems.map((i) => i.type)))
    : [];

  return (
    <div style={styles.page}>
      <Breadcrumbs industrySlug={industry.slug} />
      <div style={styles.inner}>
        <h1 style={{ ...styles.title, marginTop: 0 }}>{industry.title}</h1>
        <div style={styles.desc}>{industry.description}</div>
        <div style={styles.grid}>
          <DeployOption href={industry.demoId ? `/demos/${industry.demoId}` : "#"} enabled={!!industry.demoId}>
            <div style={styles.card}>
              <h2 style={{ ...styles.cardTitle, marginTop: 0 }}>Standard Deployment</h2>
              <div style={styles.cardDesc}>Preconfigured, ready-to-deploy solution for this industry.</div>
              {uniqueTypes.length > 0 && (
                <div style={styles.itemStrip}>
                  <span style={styles.itemStripLabel}>Includes</span>
                  {uniqueTypes.map((t) => (
                    <span key={t} style={styles.itemStripIcon} title={t}>
                      <FabricItemIcon type={t} size={16} />
                    </span>
                  ))}
                </div>
              )}
            </div>
          </DeployOption>
          <DeployOption
            href={industry.demoId ? `/demos/${industry.demoId}?mode=custom` : "#"}
            enabled={!!industry.demoId}
          >
            <div style={styles.card}>
              <h2 style={{ ...styles.cardTitle, marginTop: 0 }}>Custom Deployment</h2>
              <div style={styles.cardDesc}>
                {industry.demoId
                  ? "Choose a deployment pattern — shortcut, real-time, AI, and more."
                  : "Customizable deployment (coming soon)."}
              </div>
            </div>
          </DeployOption>
        </div>
      </div>
    </div>
  );
}

import { notFound } from "next/navigation";
import Link from "next/link";
import { industries } from "@/lib/industryCatalog";
import { Breadcrumbs } from "@/lib/Breadcrumbs";

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
} as const;

export function generateStaticParams() {
  return industries.filter((i) => i.enabled).map((i) => ({ industry: i.slug }));
}

export default async function IndustryPage({ params }: { params: Promise<{ industry: string }> }) {
  const { industry: industrySlug } = await params;
  const industry = industries.find((i) => i.slug === industrySlug && i.enabled);
  if (!industry) return notFound();

  return (
    <div style={styles.page}>
      <Breadcrumbs industrySlug={industry.slug} />
      <div style={styles.inner}>
        <div style={styles.title}>{industry.title}</div>
        <div style={styles.desc}>{industry.description}</div>
        <div style={styles.grid}>
          <Link href={industry.demoId ? `/demos/${industry.demoId}` : '#'} style={{ textDecoration: "none", pointerEvents: industry.demoId ? undefined : "none", opacity: industry.demoId ? 1 : 0.5 }}>
            <div style={styles.card}>
              <div style={styles.cardTitle}>Standard Deployment</div>
              <div style={styles.cardDesc}>Preconfigured, ready-to-deploy solution for this industry.</div>
            </div>
          </Link>
          <Link href="#" style={{ textDecoration: "none", pointerEvents: "none", opacity: 0.5 }}>
            <div style={styles.card}>
              <div style={styles.cardTitle}>Custom Deployment</div>
              <div style={styles.cardDesc}>Customizable deployment (coming soon).</div>
            </div>
          </Link>
        </div>
      </div>
    </div>
  );
}

import Link from "next/link";
import { industries } from "@/lib/industryCatalog";

export function Breadcrumbs({
  industrySlug,
  deploymentType,
  scenarioTitle,
  demoId,
}: {
  industrySlug?: string;
  deploymentType?: "standard" | "custom";
  scenarioTitle?: string;
  demoId?: string;
}) {
  const crumbs: Array<{ label: string; href?: string }> = [
    { label: "Industries", href: "/" },
  ];
  if (industrySlug) {
    const industry = industries.find((i) => i.slug === industrySlug);
    if (industry)
      crumbs.push({
        label: industry.title,
        href: `/industries/${industry.slug}`,
      });
    if (deploymentType) {
      const label = deploymentType === "standard" ? "Standard Deployment" : "Custom Deployment";
      // Link back to the demo page (with mode param) only when there is a further crumb
      const href = scenarioTitle && demoId
        ? `/demos/${demoId}?mode=${deploymentType}`
        : undefined;
      crumbs.push({ label, href });
    }
    if (scenarioTitle) {
      crumbs.push({ label: scenarioTitle });
    }
  }

  return (
    <nav
      aria-label="Breadcrumb"
      style={{
        position: "sticky",
        top: "48px",
        zIndex: 40,
        width: "100%",
        backgroundColor: "#010409",
        borderBottom: "1px solid #21262d",
        padding: "10px 40px",
        fontSize: "13px",
        color: "#8b949e",
        boxSizing: "border-box",
      }}
    >
      {crumbs.map((c, i) =>
        c.href ? (
          <span key={i}>
            <Link href={c.href} style={{ color: "#3fb68b", textDecoration: "none" }}>
              {c.label}
            </Link>
            {i < crumbs.length - 1 && (
              <span style={{ margin: "0 8px", color: "#3fb68b", fontSize: "14px" }}>›</span>
            )}
          </span>
        ) : (
          <span key={i} style={{ color: "#e6edf3" }}>
            {c.label}
            {i < crumbs.length - 1 && (
              <span style={{ margin: "0 8px", color: "#3fb68b", fontSize: "14px" }}>›</span>
            )}
          </span>
        )
      )}
    </nav>
  );
}

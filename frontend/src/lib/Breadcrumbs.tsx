import Link from "next/link";
import { industries } from "@/lib/industryCatalog";

export function Breadcrumbs({
  industrySlug,
  deploymentType,
  scenarioTitle,
  demoId,
  pageName,
}: {
  industrySlug?: string;
  deploymentType?: "standard" | "custom";
  scenarioTitle?: string;
  demoId?: string;
  pageName?: string;
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
  } else if (pageName) {
    crumbs.push({ label: pageName });
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
      {crumbs.map((c, i) => {
        const isLast = i === crumbs.length - 1;
        const sep = !isLast && (
          <span aria-hidden="true" style={{ margin: "0 8px", color: "#3fb68b", fontSize: "14px" }}>›</span>
        );
        return c.href ? (
          <span key={i}>
            <Link href={c.href} style={{ color: "#3fb68b", textDecoration: "none" }}>
              {c.label}
            </Link>
            {sep}
          </span>
        ) : (
          <span key={i} style={{ color: "#e6edf3" }} aria-current={isLast ? "page" : undefined}>
            {c.label}
            {sep}
          </span>
        );
      })}
    </nav>
  );
}

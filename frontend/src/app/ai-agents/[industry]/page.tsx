import { Suspense } from "react";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import AgentPackClient from "./AgentPackClient";
import { AGENT_PACKS } from "@/lib/agentPacks";
import { industries } from "@/lib/industryCatalog";

export function generateStaticParams() {
  return Object.keys(AGENT_PACKS).map((industry) => ({ industry }));
}

export async function generateMetadata({ params }: { params: Promise<{ industry: string }> }): Promise<Metadata> {
  const { industry } = await params;
  const pack = AGENT_PACKS[industry];
  if (!pack) return {};
  const description = `${pack.description} Deploy them to your own Azure subscription in one click.`;
  return {
    title: pack.title,
    description,
    alternates: { canonical: `/ai-agents/${industry}/` },
    openGraph: {
      title: `${pack.title} | Fabric Demo Gallery`,
      description,
      url: `https://www.fabricdemogallery.com/ai-agents/${industry}/`,
      siteName: "Fabric Demo Gallery",
      type: "website",
      images: [{ url: "/og-card.png", width: 1200, height: 630, alt: "Fabric Demo Gallery" }],
    },
  };
}

export default async function AgentPackPage({ params }: { params: Promise<{ industry: string }> }) {
  const { industry } = await params;
  const pack = AGENT_PACKS[industry];
  if (!pack) return notFound();
  const industryInfo = industries.find((i) => i.slug === pack.industrySlug);
  const breadcrumbLd = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "Demos", item: "https://www.fabricdemogallery.com/" },
      ...(industryInfo
        ? [{ "@type": "ListItem", position: 2, name: industryInfo.title, item: `https://www.fabricdemogallery.com/industries/${industryInfo.slug}/` }]
        : []),
      { "@type": "ListItem", position: industryInfo ? 3 : 2, name: pack.title },
    ],
  };
  return (
    <div>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(breadcrumbLd) }} />
      <Suspense>
        <AgentPackClient packId={industry} />
      </Suspense>
    </div>
  );
}

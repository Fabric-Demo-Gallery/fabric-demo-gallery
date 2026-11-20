import { Suspense } from "react";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import AppDetailClient from "./AppDetailClient";
import { APPS } from "@/lib/appsCatalog";
import { industries } from "@/lib/industryCatalog";

export function generateStaticParams() {
  return Object.keys(APPS).map((id) => ({ id }));
}

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  const app = APPS[id];
  if (!app) return {};
  const title = `${app.title} - Apps & AI`;
  const description = `${app.description} Deploy it to your own Azure subscription in one click.`;
  return {
    title,
    description,
    alternates: { canonical: `/apps/${id}/` },
    openGraph: {
      title: `${title} | Fabric Demo Gallery`,
      description,
      url: `https://www.fabricdemogallery.com/apps/${id}/`,
      siteName: "Fabric Demo Gallery",
      type: "website",
      images: [{ url: "/og-card.png", width: 1200, height: 630, alt: "Fabric Demo Gallery" }],
    },
  };
}

export default async function AppDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const app = APPS[id];
  if (!app) return notFound();
  const industry = industries.find((i) => i.slug === app.industrySlug);
  const breadcrumbLd = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "Demos", item: "https://www.fabricdemogallery.com/" },
      ...(industry
        ? [{ "@type": "ListItem", position: 2, name: industry.title, item: `https://www.fabricdemogallery.com/industries/${industry.slug}/` }]
        : []),
      { "@type": "ListItem", position: industry ? 3 : 2, name: app.title },
    ],
  };
  return (
    <div>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(breadcrumbLd) }} />
      <Suspense>
        <AppDetailClient id={id} />
      </Suspense>
    </div>
  );
}

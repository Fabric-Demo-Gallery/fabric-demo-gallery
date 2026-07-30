import { Suspense } from "react";
import type { Metadata } from "next";
import DemoDetailClient from "./DemoDetailClient";
import { DEMOS } from "@/lib/demoCatalog";
import { industries } from "@/lib/industryCatalog";

export function generateStaticParams() {
  return Object.keys(DEMOS).map((id) => ({ id }));
}

// Per-demo title/description so browser tabs, search results, and shared
// links (Teams/Outlook cards) identify the specific demo instead of the
// generic site name.
export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  const demo = DEMOS[id];
  if (!demo) return {};
  const title = `${demo.title} - ${demo.industry}`;
  // Bing flags descriptions under ~150 chars; catalog blurbs are short, so
  // append the deploy CTA (same pattern as industry pages). UI text untouched.
  // Skip the CTA when the blurb is already long enough on its own.
  const enriched = `${demo.description} Deploy this demo to your Microsoft Fabric tenant in one click - no setup required.`;
  const description =
    enriched.length <= 200
      ? enriched
      : demo.description.length > 200
        ? `${demo.description.slice(0, 197)}…`
        : demo.description;
  return {
    title,
    description,
    alternates: { canonical: `/demos/${id}/` },
    openGraph: {
      title: `${title} | Fabric Demo Gallery`,
      description,
      url: `https://www.fabricdemogallery.com/demos/${id}/`,
      siteName: "Fabric Demo Gallery",
      type: "website",
      images: [{ url: "/og-card.png", width: 1200, height: 630, alt: "Fabric Demo Gallery" }],
    },
    twitter: {
      card: "summary_large_image",
      title: `${title} | Fabric Demo Gallery`,
      description,
      images: ["/og-card.png"],
    },
  };
}

export default async function DemoDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const demo = DEMOS[id];
  const industry = industries.find((i) => i.demoId === id);
  // Breadcrumb structured data mirroring the visible trail - Bing (and Google)
  // use it for breadcrumb rich results and AI answers. Purely additive markup.
  const breadcrumbLd = demo
    ? {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        itemListElement: [
          { "@type": "ListItem", position: 1, name: "Demos", item: "https://www.fabricdemogallery.com/" },
          ...(industry
            ? [{ "@type": "ListItem", position: 2, name: industry.title, item: `https://www.fabricdemogallery.com/industries/${industry.slug}/` }]
            : []),
          { "@type": "ListItem", position: industry ? 3 : 2, name: demo.title },
        ],
      }
    : null;
  return (
    <div>
      {breadcrumbLd && (
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(breadcrumbLd) }} />
      )}
      <Suspense>
        <DemoDetailClient />
      </Suspense>
    </div>
  );
}

import { Suspense } from "react";
import DemoDetailClient from "./DemoDetailClient";
import { Breadcrumbs } from "@/lib/Breadcrumbs";
import { industries } from "@/lib/industryCatalog";

export function generateStaticParams() {
  return [
    { id: "manufacturing-qc" },
    { id: "retail-sales" },
    { id: "energy-grid" },
  ];
}

export default async function DemoDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const industry = industries.find((i) => i.demoId === id);
  return (
    <div>
      {industry && <Breadcrumbs industrySlug={industry.slug} deploymentType="standard" />}
      <Suspense>
        <DemoDetailClient />
      </Suspense>
    </div>
  );
}

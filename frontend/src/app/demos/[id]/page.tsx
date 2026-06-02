import { Suspense } from "react";
import DemoDetailClient from "./DemoDetailClient";
import { DEMOS } from "@/lib/demoCatalog";
import { Breadcrumbs } from "@/lib/Breadcrumbs";
import { industries } from "@/lib/industryCatalog";

export function generateStaticParams() {
  return Object.keys(DEMOS).map((id) => ({ id }));
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

import DemoDetailClient from "./DemoDetailClient";

export function generateStaticParams() {
  return [
    { id: "manufacturing-qc" },
    { id: "retail-sales" },
    { id: "energy-grid" },
  ];
}

export default function DemoDetailPage() {
  return <DemoDetailClient />;
}

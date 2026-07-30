import type { Metadata } from "next";

// The monitoring page itself is a client component and can't export metadata -
// this layout gives it a unique title/description (it previously inherited the
// site default, which Bing flagged as a duplicate title with the home page).
export const metadata: Metadata = {
  title: "Live Deployment Monitoring",
  description:
    "Watch Microsoft Fabric demo deployments in real time - workspace creation, lakehouses, notebooks, pipelines and Power BI reports as they roll out to your tenant.",
  alternates: { canonical: "/monitoring/" },
};

export default function MonitoringLayout({ children }: { children: React.ReactNode }) {
  return children;
}

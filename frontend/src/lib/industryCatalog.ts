// Central catalog for industries, use cases, and demo mappings

export interface Industry {
  slug: string;
  title: string;
  description: string;
  icon: string; // Icon file name or Fluent UI icon name
  enabled: boolean;
  demoId?: string; // For mapped demo
  features?: string[]; // Feature tags for filtering
}

export const industries: Industry[] = [
  {
    slug: "manufacturing",
    title: "Manufacturing",
    description: "Analytics and optimization for factories, production lines, and supply chains.",
    icon: "/fabric-logo.png",
    enabled: true,
    demoId: "manufacturing-qc",
    features: ["Power BI"],
  },
  {
    slug: "retail",
    title: "Retail",
    description: "Sales, inventory, and customer analytics for retail organizations.",
    icon: "/fabric-logo.png",
    enabled: true,
    demoId: "retail-sales",
    features: ["Power BI"],
  },
  {
    slug: "energy",
    title: "Energy & Utilities",
    description: "Grid, asset, and renewable analytics for energy providers.",
    icon: "/fabric-logo.png",
    enabled: true,
    demoId: "energy-grid",
    features: ["RTI", "Power BI"],
  },
  {
    slug: "financial-services",
    title: "Financial Services",
    description: "Banking, insurance, and capital markets analytics.",
    icon: "/fabric-logo.png",
    enabled: true,
  },
  {
    slug: "professional-services",
    title: "Professional Services",
    description: "Consulting, legal, and business services analytics.",
    icon: "/fabric-logo.png",
    enabled: true,
  },
  {
    slug: "healthcare",
    title: "Healthcare & Life Sciences",
    description: "Patient, provider, and research analytics for healthcare organizations.",
    icon: "/fabric-logo.png",
    enabled: true,
  },
  {
    slug: "technology",
    title: "Technology & Software",
    description: "Analytics for software, SaaS, and technology companies.",
    icon: "/fabric-logo.png",
    enabled: true,
  },
  {
    slug: "transportation",
    title: "Transportation & Logistics",
    description: "Fleet, route, and logistics analytics for transportation providers.",
    icon: "/fabric-logo.png",
    enabled: true,
  },
  {
    slug: "construction",
    title: "Construction & Real Estate",
    description: "Project, asset, and property analytics for construction and real estate.",
    icon: "/fabric-logo.png",
    enabled: true,
  },
  {
    slug: "media",
    title: "Media, Telecommunications & Entertainment",
    description: "Audience, content, and ad analytics for media and entertainment.",
    icon: "/fabric-logo.png",
    enabled: true,
  },
  {
    slug: "education",
    title: "Education",
    description: "Student, faculty, and learning analytics for education organizations.",
    icon: "/fabric-logo.png",
    enabled: true,
  },
  {
    slug: "hospitality",
    title: "Hospitality & Travel",
    description: "Guest, booking, and operations analytics for hospitality and travel.",
    icon: "/fabric-logo.png",
    enabled: true,
  },
];

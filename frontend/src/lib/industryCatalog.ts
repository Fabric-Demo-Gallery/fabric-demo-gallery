// Central catalog for industries, use cases, and demo mappings

export interface Industry {
  slug: string;
  title: string;
  description: string;
  icon: string; // Icon file name or Fluent UI icon name
  enabled: boolean;
  demoId?: string; // For mapped demo
}

export const industries: Industry[] = [
  {
    slug: "manufacturing",
    title: "Manufacturing",
    description: "Analytics and optimization for factories, production lines, and supply chains.",
    icon: "factory.svg",
    enabled: true,
    demoId: "manufacturing-qc",
  },
  {
    slug: "retail",
    title: "Retail",
    description: "Sales, inventory, and customer analytics for retail organizations.",
    icon: "store.svg",
    enabled: true,
    demoId: "retail-sales",
  },
  {
    slug: "energy",
    title: "Energy & Utilities",
    description: "Grid, asset, and renewable analytics for energy providers.",
    icon: "bolt.svg",
    enabled: true,
    demoId: "energy-grid",
  },
  {
    slug: "financial-services",
    title: "Financial Services",
    description: "Banking, insurance, and capital markets analytics.",
    icon: "financial.svg",
    enabled: true,
    demoId: "financial-services",
  },
  {
    slug: "professional-services",
    title: "Professional Services",
    description: "Consulting, legal, and business services analytics.",
    icon: "briefcase.svg",
    enabled: true,
    demoId: "professional-services",
  },
  {
    slug: "healthcare",
    title: "Healthcare & Life Sciences",
    description: "Patient, provider, and research analytics for healthcare organizations.",
    icon: "healthcare.svg",
    enabled: true,
    demoId: "healthcare",
  },
  {
    slug: "technology",
    title: "Technology & Software",
    description: "Analytics for software, SaaS, and technology companies.",
    icon: "chip.svg",
    enabled: true,
    demoId: "technology",
  },
  {
    slug: "transportation",
    title: "Transportation & Logistics",
    description: "Fleet, route, and logistics analytics for transportation providers.",
    icon: "truck.svg",
    enabled: true,
    demoId: "transportation",
  },
  {
    slug: "construction",
    title: "Construction & Real Estate",
    description: "Project, asset, and property analytics for construction and real estate.",
    icon: "building.svg",
    enabled: true,
    demoId: "construction",
  },
  {
    slug: "media",
    title: "Media, Telecommunications & Entertainment",
    description: "Audience, content, and ad analytics for media and entertainment.",
    icon: "media.svg",
    enabled: true,
    demoId: "media",
  },
  {
    slug: "education",
    title: "Education",
    description: "Student, faculty, and learning analytics for education organizations.",
    icon: "education.svg",
    enabled: true,
    demoId: "education",
  },
  {
    slug: "hospitality",
    title: "Hospitality & Travel",
    description: "Guest, booking, and operations analytics for hospitality and travel.",
    icon: "hotel.svg",
    enabled: true,
    demoId: "hospitality",
  },
];

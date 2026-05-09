"use client";

import { useState } from "react";

const DEMOS = [
  {
    id: "manufacturing-qc",
    industry: "Manufacturing",
    title: "Quality Control Analytics",
    desc: "End-to-end OEE tracking, defect analysis, equipment health monitoring, and shift performance analytics across production lines. Includes 6 Gold tables, 30+ DAX measures, and a 4-page Power BI dashboard.",
    tags: ["Medallion Architecture", "IoT Sensors", "OEE", "PySpark", "Direct Lake"],
    time: "8–12 min",
    itemCount: 10,
  },
  {
    id: "retail-sales",
    industry: "Retail",
    title: "Sales & Inventory Analytics",
    desc: "Revenue trends, basket analysis, margin tracking, inventory turnover, and stockout risk analytics across stores and categories. Includes 2 Gold tables, 14 DAX measures, and a 3-page Power BI dashboard.",
    tags: ["Medallion Architecture", "POS Data", "Star Schema", "PySpark", "Direct Lake"],
    time: "8–12 min",
    itemCount: 7,
  },
];

export default function Home() {
  const [filter, setFilter] = useState("All");
  const industries = ["All", ...new Set(DEMOS.map((d) => d.industry))];
  const filtered = filter === "All" ? DEMOS : DEMOS.filter((d) => d.industry === filter);

  return (
    <>
      {/* Hero banner */}
      <div className="bg-gradient-to-b from-[#0f6cbd] to-[#0a5199]">
        <div className="mx-auto max-w-[1280px] px-8 py-14">
          <p className="text-[13px] font-medium text-white/70 uppercase tracking-wider mb-2">Microsoft Fabric</p>
          <h1 className="text-[32px] font-bold text-white leading-tight max-w-lg">
            Industry Demo Gallery
          </h1>
          <p className="mt-3 text-[16px] text-white/80 max-w-xl leading-relaxed">
            Deploy complete analytics environments — lakehouse, notebooks, semantic models, Power BI dashboards, and pipelines — into your Fabric tenant with one click.
          </p>
        </div>
      </div>

      {/* Content */}
      <div className="mx-auto max-w-[1280px] px-8 py-8">
        {/* Breadcrumb + filter */}
        <div className="flex items-center justify-between mb-6">
          <nav className="text-[13px] text-[#616161]">
            <span className="text-[#0f6cbd]">Home</span>
            <span className="mx-2 text-[#d1d1d1]">/</span>
            <span>Demos</span>
          </nav>
          <div className="flex bg-white rounded-[4px] border border-[#e0e0e0] overflow-hidden">
            {industries.map((ind) => (
              <button
                key={ind}
                onClick={() => setFilter(ind)}
                className={`px-4 py-[6px] text-[13px] font-medium transition-colors ${
                  filter === ind
                    ? "bg-[#0f6cbd] text-white"
                    : "text-[#424242] hover:bg-[#f5f5f5]"
                }`}
              >
                {ind}
              </button>
            ))}
          </div>
        </div>

        {/* Cards */}
        <div className="grid gap-5 md:grid-cols-2 mb-12">
          {filtered.map((demo) => (
            <a
              key={demo.id}
              href={`/demos/${demo.id}`}
              className="group block bg-white rounded-[8px] border border-[#e0e0e0] overflow-hidden hover:shadow-[0_2px_12px_rgba(0,0,0,0.08)] hover:border-[#c7c7c7] transition-all hover:no-underline"
            >
              {/* Card header with blue accent */}
              <div className="h-[4px] bg-[#0f6cbd]" />
              <div className="p-6">
                <div className="flex items-center gap-2 mb-3">
                  <span className="text-[12px] font-semibold text-[#0f6cbd] bg-[#ebf3fc] rounded-[4px] px-2 py-[2px]">
                    {demo.industry}
                  </span>
                  <span className="text-[12px] text-[#9e9e9e]">{demo.time}</span>
                  <span className="text-[12px] text-[#9e9e9e]">{demo.itemCount} Fabric items</span>
                </div>

                <h2 className="text-[18px] font-semibold text-[#242424] mb-2 group-hover:text-[#0f6cbd] transition-colors">
                  {demo.title}
                </h2>
                <p className="text-[14px] text-[#616161] leading-relaxed mb-4">
                  {demo.desc}
                </p>

                {/* Tags */}
                <div className="flex flex-wrap gap-[6px]">
                  {demo.tags.map((tag) => (
                    <span key={tag} className="text-[12px] text-[#616161] bg-[#f5f5f5] rounded-[4px] px-[8px] py-[3px] border border-[#e8e8e8]">
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            </a>
          ))}
        </div>

        {/* How it works */}
        <div className="bg-white rounded-[8px] border border-[#e0e0e0] p-8 mb-12">
          <h2 className="text-[20px] font-semibold text-[#242424] mb-6">How it works</h2>
          <div className="grid grid-cols-4 gap-0 relative">
            {/* Connector line */}
            <div className="absolute top-[18px] left-[36px] right-[36px] h-[2px] bg-[#e0e0e0]" />
            {[
              { n: 1, t: "Browse", d: "Choose an industry demo from the gallery" },
              { n: 2, t: "Authenticate", d: "Sign in with your Microsoft Entra account" },
              { n: 3, t: "Configure", d: "Name your workspace and select a Fabric capacity" },
              { n: 4, t: "Deploy", d: "Watch real-time progress as each item is provisioned" },
            ].map(({ n, t, d }) => (
              <div key={n} className="relative text-center px-4">
                <div className="mx-auto w-[36px] h-[36px] rounded-full bg-[#0f6cbd] flex items-center justify-center text-white text-[14px] font-bold mb-3 relative z-10">
                  {n}
                </div>
                <div className="text-[14px] font-semibold text-[#242424] mb-1">{t}</div>
                <div className="text-[13px] text-[#616161] leading-snug">{d}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}

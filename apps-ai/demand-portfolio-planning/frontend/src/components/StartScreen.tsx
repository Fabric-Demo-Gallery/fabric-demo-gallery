import { useMemo, useState } from "react";
import { useT } from "../I18nProvider";
import type { SeedDemand } from "../types";
import { Legend } from "./Provenance";

type StartArgs = { demandId?: string; rawDemand?: string };
type Mode = "samples" | "custom";

function DemandIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="3" y="3" width="18" height="18" rx="4" stroke="currentColor" strokeWidth="1.6" />
      <path d="M7 9h10M7 13h7" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

export function StartScreen({
  demands,
  portfolioCount,
  poolCount,
  starting,
  onStart,
}: {
  demands: SeedDemand[];
  portfolioCount: number;
  poolCount: number;
  starting: boolean;
  onStart: (args: StartArgs) => void;
}) {
  const t = useT();
  const [mode, setMode] = useState<Mode>("samples");
  const [selected, setSelected] = useState<string>(demands[0]?.demand_id ?? "");
  const [customText, setCustomText] = useState<string>("");

  const selectedDemand = useMemo(
    () => demands.find((d) => d.demand_id === selected),
    [demands, selected],
  );

  const canStart =
    !starting && (mode === "custom" ? customText.trim().length > 0 : Boolean(selected));

  const start = () => {
    if (!canStart) return;
    if (mode === "custom") {
      onStart({ rawDemand: customText.trim() });
    } else if (selected) {
      onStart({ demandId: selected });
    }
  };

  return (
    <div className="start">
      <div className="start-main">
        <h1 className="start-heading">{t("start.heading")}</h1>
        <p className="start-sub">{t("start.sub")}</p>

        <div className="segmented" role="tablist" aria-label="intake mode">
          <button
            type="button"
            role="tab"
            aria-selected={mode === "samples"}
            className={mode === "samples" ? "on" : ""}
            onClick={() => setMode("samples")}
          >
            {t("start.tab.samples")}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === "custom"}
            className={mode === "custom" ? "on" : ""}
            onClick={() => setMode("custom")}
          >
            {t("start.tab.custom")}
          </button>
        </div>

        {mode === "samples" ? (
          <>
            <div className="demand-list">
              {demands.map((d) => (
                <button
                  key={d.demand_id}
                  className={`demand-card${selected === d.demand_id ? " demand-card-selected" : ""}`}
                  onClick={() => setSelected(d.demand_id)}
                  type="button"
                >
                  <span className="demand-icon">
                    <DemandIcon />
                  </span>
                  <span className="demand-card-body">
                    <span className="demand-card-title">{d.title}</span>
                    {d.known_process_owner && (
                      <span className="demand-card-owner">
                        {t("start.owner")}: {d.known_process_owner}
                      </span>
                    )}
                    <span className="demand-card-snippet">{d.raw_demand}</span>
                  </span>
                  <span className="demand-card-chevron">›</span>
                </button>
              ))}
            </div>

            {selectedDemand && (
              <div className="raw-preview">
                <span className="raw-preview-label">{t("start.rawLabel")}</span>
                <p className="raw-preview-text">{selectedDemand.raw_demand}</p>
              </div>
            )}
          </>
        ) : (
          <div className="custom-demand">
            <label className="raw-preview-label" htmlFor="custom-demand-text">
              {t("start.customLabel")}
            </label>
            <textarea
              id="custom-demand-text"
              className="custom-demand-input"
              value={customText}
              onChange={(e) => setCustomText(e.target.value)}
              placeholder={t("start.customPlaceholder")}
              rows={6}
            />
            <p className="custom-hint">{t("start.customHint")}</p>
          </div>
        )}

        <button
          className="btn btn-primary btn-lg"
          disabled={!canStart}
          onClick={start}
          type="button"
        >
          {starting ? t("start.starting") : t("start.cta")} <span aria-hidden="true">→</span>
        </button>

        <Legend />
      </div>

      <aside className="start-rail">
        <div className="tile">
          <span className="tile-label">{t("start.portfolio")}</span>
          <span className="tile-value">
            {portfolioCount} {t("start.projects")}
          </span>
        </div>
        <div className="tile">
          <span className="tile-label">{t("start.pool")}</span>
          <span className="tile-value">
            {poolCount} {t("start.people")}
          </span>
        </div>
      </aside>
    </div>
  );
}

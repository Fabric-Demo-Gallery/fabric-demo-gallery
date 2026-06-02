"use client";

import { createContext, useContext, useState, useRef, useCallback } from "react";
import type { ReactNode } from "react";
import { createJob } from "@/lib/api";

export type DeployStep = {
  name: string;
  description: string;
  status: "pending" | "running" | "completed" | "failed";
  detail?: string | null;
};

interface DeploymentState {
  demoId: string | null;
  jobId: string | null;
  deploying: boolean;
  steps: DeployStep[];
  error: string | null;
  completed: boolean;
  deployedWorkspaceId: string;
  cleaning: boolean;
  cleaned: boolean;
}

interface DeploymentContextValue extends DeploymentState {
  startDeploy: (params: {
    demoId: string;
    workspaceName: string;
    capacityId?: string;
    features?: string[];
    fabricToken: string;
    storageToken: string;
  }) => Promise<void>;
  reconnectJob: (jobId: string, demoId: string, fabricToken: string) => void;
  stopDeploy: () => void;
  resetState: () => void;
  setCleaning: (v: boolean) => void;
  setCleaned: (v: boolean) => void;
  setDeployedWorkspaceId: (v: string) => void;
  setError: (v: string | null) => void;
}

const initialState: DeploymentState = {
  demoId: null,
  jobId: null,
  deploying: false,
  steps: [],
  error: null,
  completed: false,
  deployedWorkspaceId: "",
  cleaning: false,
  cleaned: false,
};

const DeploymentContext = createContext<DeploymentContextValue | null>(null);

export function useDeployment() {
  const ctx = useContext(DeploymentContext);
  if (!ctx) throw new Error("useDeployment must be used within DeploymentProvider");
  return ctx;
}

export function DeploymentProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<DeploymentState>(initialState);
  const abortRef = useRef<AbortController | null>(null);

  /** Subscribe to a job's SSE stream (replay + live). */
  const subscribeToJob = useCallback((jobId: string, fabricToken: string) => {
    // Abort any existing subscription
    if (abortRef.current) {
      abortRef.current.abort();
    }

    const controller = new AbortController();
    abortRef.current = controller;

    const API = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

    (async () => {
      try {
        const resp = await fetch(`${API}/api/jobs/${jobId}/stream`, {
          headers: { Authorization: `Bearer ${fabricToken}` },
          signal: controller.signal,
        });

        if (!resp.ok) {
          const text = await resp.text();
          setState((prev) => ({
            ...prev,
            error: `Stream error ${resp.status}: ${text.slice(0, 200)}`,
            deploying: false,
          }));
          abortRef.current = null;
          return;
        }

        const reader = resp.body?.getReader();
        const decoder = new TextDecoder();
        if (!reader) {
          setState((prev) => ({ ...prev, error: "No response stream", deploying: false }));
          abortRef.current = null;
          return;
        }

        let buffer = "";
        let currentEvent = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            if (line.startsWith("event: ")) {
              currentEvent = line.slice(7).trim();
            } else if (line.startsWith("data: ")) {
              if (currentEvent === "ping") {
                currentEvent = "";
                continue;
              }
              try {
                const data = JSON.parse(line.slice(6));
                if (currentEvent === "plan") {
                  setState((prev) => ({ ...prev, steps: data as DeployStep[] }));
                } else if (currentEvent === "step") {
                  const step = data as DeployStep;
                  setState((prev) => {
                    const newSteps = prev.steps.map((s) =>
                      s.name === step.name ? { ...s, ...step } : s
                    );
                    const updates: Partial<DeploymentState> = { steps: newSteps };
                    if (step.name === "done" && step.status === "completed") {
                      updates.completed = true;
                      updates.deploying = false;
                      if (step.detail) {
                        try {
                          const info = JSON.parse(step.detail as string);
                          if (info.workspaceId) updates.deployedWorkspaceId = info.workspaceId;
                        } catch { /* detail might not be JSON */ }
                      }
                    }
                    if (step.name === "workspace" && (step as Record<string, unknown>).itemId) {
                      updates.deployedWorkspaceId = (step as Record<string, unknown>).itemId as string;
                    }
                    return { ...prev, ...updates };
                  });
                } else if (currentEvent === "error") {
                  setState((prev) => ({
                    ...prev,
                    error: data.message || "Deployment failed",
                    deploying: false,
                    deployedWorkspaceId: data.workspaceId || prev.deployedWorkspaceId,
                  }));
                }
              } catch {
                // ignore malformed data lines
              }
              currentEvent = "";
            }
          }
        }

        // Stream ended normally
        setState((prev) => ({
          ...prev,
          completed: prev.completed || true,
          deploying: false,
        }));
      } catch (e: unknown) {
        if (e instanceof DOMException && e.name === "AbortError") {
          // User disconnected — deployment continues on backend
          return;
        }
        setState((prev) => ({
          ...prev,
          error: e instanceof Error ? e.message : "Connection failed",
          deploying: false,
        }));
      } finally {
        abortRef.current = null;
      }
    })();
  }, []);

  const startDeploy = useCallback(
    async (params: {
      demoId: string;
      workspaceName: string;
      capacityId?: string;
      features?: string[];
      fabricToken: string;
      storageToken: string;
    }) => {
      // If already deploying, don't start another
      if (abortRef.current) return;

      setState({
        ...initialState,
        demoId: params.demoId,
        deploying: true,
      });

      try {
        const { job_id } = await createJob(
          params.fabricToken,
          params.storageToken,
          {
            demoId: params.demoId,
            workspaceName: params.workspaceName,
            capacityId: params.capacityId,
            features: params.features,
          }
        );

        setState((prev) => ({ ...prev, jobId: job_id }));
        subscribeToJob(job_id, params.fabricToken);
      } catch (e: unknown) {
        setState((prev) => ({
          ...prev,
          error: e instanceof Error ? e.message : "Failed to create deployment job",
          deploying: false,
        }));
      }
    },
    [subscribeToJob]
  );

  const reconnectJob = useCallback(
    (jobId: string, demoId: string, fabricToken: string) => {
      setState((prev) => ({
        ...prev,
        jobId,
        demoId,
        deploying: true,
        steps: [],
        error: null,
        completed: false,
      }));
      subscribeToJob(jobId, fabricToken);
    },
    [subscribeToJob]
  );

  const stopDeploy = useCallback(() => {
    // Only disconnects the SSE subscription — backend job continues running
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
  }, []);

  const resetState = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    setState(initialState);
  }, []);

  return (
    <DeploymentContext.Provider
      value={{
        ...state,
        startDeploy,
        reconnectJob,
        stopDeploy,
        resetState,
        setCleaning: (v) => setState((prev) => ({ ...prev, cleaning: v })),
        setCleaned: (v) => setState((prev) => ({ ...prev, cleaned: v })),
        setDeployedWorkspaceId: (v) => setState((prev) => ({ ...prev, deployedWorkspaceId: v })),
        setError: (v) => setState((prev) => ({ ...prev, error: v })),
      }}
    >
      {children}
    </DeploymentContext.Provider>
  );
}

const API_BASE = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

export interface Demo {
  id: string;
  industry: string;
  title: string;
  description: string;
  estimatedTime: string;
  icon: string;
  items: { type: string; name: string }[];
}

export interface DemoDetail {
  id: string;
  industry: string;
  title: string;
  description: string;
  longDescription: string;
  icon: string;
  estimatedTime: string;
  prerequisites: string[];
  architecture: { pattern: string; layers: string[] };
  sampleData: { fileName: string; description: string; format: string; rows: number }[];
  fabricItems: {
    type: string;
    name: string;
    description: string;
    definitionPath?: string;
    order?: number;
  }[];
}

export interface DatasetPreview {
  fileName: string;
  columns: string[];
  rows: Record<string, string>[];
  shownRows: number;
  totalRows?: number;
}

export interface Workspace {
  id: string;
  displayName: string;
  capacityId: string | null;
}

export interface DeploymentStep {
  name: string;
  description: string;
  status: "pending" | "running" | "completed" | "failed";
  detail: string | null;
  itemId: string | null;
}

export async function fetchDemos(): Promise<Demo[]> {
  const res = await fetch(`${API_BASE}/api/demos`);
  if (!res.ok) throw new Error("Failed to fetch demos");
  return res.json();
}

export async function fetchDemo(id: string): Promise<DemoDetail> {
  const res = await fetch(`${API_BASE}/api/demos/${id}`);
  if (!res.ok) throw new Error("Failed to fetch demo");
  return res.json();
}

export async function fetchDatasetPreview(
  demoId: string,
  fileName: string
): Promise<DatasetPreview> {
  const res = await fetch(
    `${API_BASE}/api/demos/${encodeURIComponent(demoId)}/data/${encodeURIComponent(fileName)}/preview`
  );
  if (!res.ok) {
    let message = "Failed to fetch dataset preview";
    try {
      const body = await res.json();
      if (body?.detail) message = body.detail;
    } catch {
      // Keep the generic message if the backend did not return JSON.
    }
    throw new Error(message);
  }
  return res.json();
}

export async function fetchWorkspaces(token: string): Promise<Workspace[]> {
  const res = await fetch(`${API_BASE}/api/workspaces`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Failed to fetch workspaces");
  return res.json();
}

export function startDeployment(
  token: string,
  demoId: string,
  options: {
    workspaceName?: string;
    workspaceId?: string;
    capacityId?: string;
  },
  onStep: (step: DeploymentStep) => void,
  onPlan: (steps: DeploymentStep[]) => void,
  onError: (message: string) => void,
  onDone: () => void
): () => void {
  const controller = new AbortController();

  (async () => {
    try {
      const res = await fetch(`${API_BASE}/api/deploy/${demoId}`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          demo_id: demoId,
          workspace_name: options.workspaceName,
          workspace_id: options.workspaceId,
          capacity_id: options.capacityId,
        }),
        signal: controller.signal,
      });

      if (!res.ok) {
        onError(`Deployment failed: ${res.statusText}`);
        return;
      }

      const reader = res.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) return;

      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const data = JSON.parse(line.slice(6));
            // Check the event type from the preceding event: line
            onStep(data);
          } else if (line.startsWith("event: plan")) {
            // Next data line will be the plan
          } else if (line.startsWith("event: error")) {
            // Next data line will be the error
          }
        }
      }
      onDone();
    } catch (e: unknown) {
      if (e instanceof Error && e.name !== "AbortError") {
        onError(e.message);
      }
    }
  })();

  return () => controller.abort();
}

export async function teardownDeployment(
  token: string,
  workspaceId: string
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/deploy/${workspaceId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Failed to teardown deployment");
}

// ── Azure subscription / resource group helpers ──────────────────────────────

export interface AzureSubscription {
  id: string;
  displayName: string;
}

export interface AzureResourceGroup {
  name: string;
  location: string;
}

export async function fetchSubscriptions(
  managementToken: string
): Promise<AzureSubscription[]> {
  const res = await fetch(`${API_BASE}/api/azure/subscriptions`, {
    headers: { "X-Management-Token": managementToken },
  });
  if (!res.ok) throw new Error(`Failed to fetch subscriptions: ${res.statusText}`);
  return res.json();
}

export async function fetchResourceGroups(
  managementToken: string,
  subscriptionId: string
): Promise<AzureResourceGroup[]> {
  const res = await fetch(
    `${API_BASE}/api/azure/resource-groups?subscriptionId=${encodeURIComponent(subscriptionId)}`,
    { headers: { "X-Management-Token": managementToken } }
  );
  if (!res.ok) throw new Error(`Failed to fetch resource groups: ${res.statusText}`);
  return res.json();
}

// ── Deployment scenario helpers ──────────────────────────────────────────────

export interface ScenarioAzureParam {
  name: string;
  label: string;
  type: string;
  required: boolean;
  default?: string | boolean;
  description?: string;
  validation?: string;
}

export interface ScenarioInfo {
  id: string;
  title: string;
  description: string;
  estimatedTime: string;
  tags: string[];
  enabled: boolean;
  requiresAzure: boolean;
  azureParams: ScenarioAzureParam[];
  feature?: string;
  /** Scenario-specific "What to show next" pointers shown after a successful
   *  deploy. When set, these override the demo-level post-deploy guidance. */
  postDeploy?: { label: string; detail: string }[];
}

export async function fetchScenarios(demoId: string): Promise<ScenarioInfo[]> {
  const res = await fetch(`${API_BASE}/api/demos/${encodeURIComponent(demoId)}/scenarios`);
  if (!res.ok) return [];
  return res.json();
}
// ── Job-based deployment API ────────────────────────────────────────

export interface JobSummary {
  job_id: string;
  demo_id: string;
  workspace_name: string;
  scenario_id: string | null;
  status: "pending" | "running" | "completed" | "failed";
  created_at: string;
  updated_at: string;
  workspace_id: string | null;
  error: string | null;
  step_summary: {
    total: number;
    completed: number;
    failed: number;
    running: number;
  };
}

export interface JobDetail extends JobSummary {
  steps: DeploymentStep[];
}

export async function createJob(
  token: string,
  storageToken: string,
  params: {
    demoId: string;
    workspaceName?: string;
    capacityId?: string;
  }
): Promise<{ job_id: string }> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };
  if (storageToken) {
    headers["X-Storage-Token"] = storageToken;
  }
  const res = await fetch(`${API_BASE}/api/jobs`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      demo_id: params.demoId,
      workspace_name: params.workspaceName,
      capacity_id: params.capacityId || undefined,
    }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Backend error ${res.status}: ${text.slice(0, 200)}`);
  }
  return res.json();
}

export async function getJobs(token: string): Promise<JobSummary[]> {
  const res = await fetch(`${API_BASE}/api/jobs`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Failed to fetch jobs");
  return res.json();
}

export async function getJob(
  token: string,
  jobId: string
): Promise<JobDetail> {
  const res = await fetch(`${API_BASE}/api/jobs/${jobId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Failed to fetch job");
  return res.json();
}

export async function deleteJobWorkspace(
  token: string,
  jobId: string
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/jobs/${jobId}/workspace`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Failed to delete workspace: ${text.slice(0, 200)}`);
  }
}

// ── Live Eventstream replay (Real-Time Intelligence demo) ────────────────────

export interface StreamSession {
  sessionId: string;
  demoId: string;
  tableName: string;
  sent: number;
  running: boolean;
  error: string;
  startedAt: string;
}

export async function startLiveStream(params: {
  demoId: string;
  scenarioId?: string;
  connectionString: string;
  interval?: number;
  batchSize?: number;
}): Promise<StreamSession> {
  const res = await fetch(`${API_BASE}/api/stream/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      demoId: params.demoId,
      scenarioId: params.scenarioId || "real-time-intelligence",
      connectionString: params.connectionString,
      interval: params.interval ?? 1.0,
      batchSize: params.batchSize ?? 5,
    }),
  });
  if (!res.ok) {
    const text = await res.text();
    let msg = text.slice(0, 300);
    try {
      msg = JSON.parse(text).detail || msg;
    } catch {
      /* keep raw text */
    }
    throw new Error(msg);
  }
  return res.json();
}

export async function stopLiveStream(sessionId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/stream/stop`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sessionId }),
  });
  if (!res.ok) throw new Error("Failed to stop live stream");
}

export async function getStreamStatus(sessionId: string): Promise<StreamSession> {
  const res = await fetch(`${API_BASE}/api/stream/status/${encodeURIComponent(sessionId)}`);
  if (!res.ok) throw new Error("Failed to get stream status");
  return res.json();
}

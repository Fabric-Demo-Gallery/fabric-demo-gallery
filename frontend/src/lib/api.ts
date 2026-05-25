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
  icon: string;
  estimatedTime: string;
  tags: string[];
  enabled: boolean;
  requiresAzure: boolean;
  azureParams: ScenarioAzureParam[];
}

export async function fetchScenarios(demoId: string): Promise<ScenarioInfo[]> {
  const res = await fetch(`${API_BASE}/api/demos/${encodeURIComponent(demoId)}/scenarios`);
  if (!res.ok) return [];
  return res.json();
}

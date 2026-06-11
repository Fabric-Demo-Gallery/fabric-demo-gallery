// Maps raw deployment/capacity error strings to friendly, actionable guidance.
// Pattern-matched against the failure modes seen during real Fabric deploys.
// Always falls back to the raw message so no information is ever hidden.

export interface FriendlyError {
  title: string;
  guidance: string;
  /** Whether retrying the same deploy is likely to help. */
  retryable: boolean;
}

export function explainError(raw: string | null | undefined): FriendlyError {
  const msg = (raw ?? "").toString();
  const m = msg.toLowerCase();

  // Capacity paused / not active / none found
  if (
    m.includes("capacity") &&
    (m.includes("paus") || m.includes("inactive") || m.includes("suspend") || m.includes("not active") || m.includes("no active") || m.includes("no capacity"))
  ) {
    return {
      title: "Fabric capacity unavailable",
      guidance:
        "Your Fabric capacity looks paused or inactive. Resume it in the Azure portal (or pick a different active capacity), then retry.",
      retryable: true,
    };
  }

  // Spark / Livy cold-start — transient
  if (m.includes("livy") || (m.includes("spark") && (m.includes("session") || m.includes("start")))) {
    return {
      title: "Spark is warming up",
      guidance:
        "The Spark pool was cold-starting — this is transient. Wait ~30 seconds and retry; it usually succeeds on the next attempt.",
      retryable: true,
    };
  }

  // Auth / token expiry
  if (m.includes("401") || m.includes("unauthorized") || m.includes("token") && m.includes("expir")) {
    return {
      title: "Your sign-in expired",
      guidance:
        "Your Microsoft Entra session expired during deployment. Sign in again, then retry the deploy.",
      retryable: true,
    };
  }

  // Permissions
  if (m.includes("403") || m.includes("forbidden") || m.includes("permission") || m.includes("not authorized")) {
    return {
      title: "Permission denied",
      guidance:
        "Your account needs rights to create Fabric workspaces (and an assignable capacity). Check with your Fabric admin, then retry.",
      retryable: false,
    };
  }

  // Workspace name conflict
  if ((m.includes("name") && (m.includes("conflict") || m.includes("already") || m.includes("taken") || m.includes("exists"))) || m.includes("409")) {
    return {
      title: "Workspace name already in use",
      guidance:
        "A workspace with this name already exists. Choose a different workspace name and retry.",
      retryable: true,
    };
  }

  // Capacity throttling / too many requests
  if (m.includes("429") || m.includes("throttl") || m.includes("too many requests")) {
    return {
      title: "Capacity is busy",
      guidance:
        "The capacity is throttling requests right now. Wait a minute and retry — or use a less busy capacity.",
      retryable: true,
    };
  }

  // SQL endpoint / DirectLake sync lag on fresh deploys
  if (m.includes("sql") && (m.includes("endpoint") || m.includes("sync")) || m.includes("directquery") || m.includes("source tables")) {
    return {
      title: "Semantic model still syncing",
      guidance:
        "The SQL endpoint was still syncing the freshly-written tables. This usually self-resolves — retry the deploy in a moment.",
      retryable: true,
    };
  }

  // Transient network
  if (m.includes("network") || m.includes("getaddrinfo") || m.includes("timeout") || m.includes("econnreset") || m.includes("fetch failed")) {
    return {
      title: "Network hiccup",
      guidance:
        "A transient network error interrupted the deploy. Check your connection and retry.",
      retryable: true,
    };
  }

  // Generic 5xx
  if (m.includes("500") || m.includes("502") || m.includes("503") || m.includes("internal server")) {
    return {
      title: "Fabric service error",
      guidance:
        "Fabric returned a server error. This is often transient — retry shortly. If it persists, check Fabric service health.",
      retryable: true,
    };
  }

  // Fallback — show the raw message, still offer retry
  return {
    title: "Deployment failed",
    guidance: msg || "An unexpected error occurred during deployment.",
    retryable: true,
  };
}

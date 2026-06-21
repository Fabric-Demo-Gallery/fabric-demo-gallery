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

  // Invalid / too-long name (validation, not a conflict)
  if (
    m.includes("invalid character") ||
    m.includes("contains invalid") ||
    (m.includes("name") && m.includes("must be") && m.includes("character"))
  ) {
    return {
      title: "That name isn't allowed",
      guidance:
        "The name has unsupported characters or is too long (max 100 — letters, numbers, spaces, and , & _ - ( ) . only). Enter a shorter, simpler name and retry.",
      retryable: true,
    };
  }

  // Storage account name globally taken / unavailable
  if (m.includes("storage") && (m.includes("already taken") || m.includes("not available") || m.includes("alreadyexists"))) {
    return {
      title: "Storage account name taken",
      guidance:
        "Storage account names must be globally unique, and this one is in use. Leave the name blank to auto-generate one (or pick another), then retry.",
      retryable: true,
    };
  }

  // Missing Azure inputs for Azure-provisioning scenarios
  if (m.includes("requires subscription") || m.includes("azure credentials") || (m.includes("subscription") && m.includes("required"))) {
    return {
      title: "Azure details needed",
      guidance:
        "This scenario provisions Azure resources, so it needs an Azure subscription, a resource group, and sign-in. Select those, then retry.",
      retryable: true,
    };
  }

  // Model / resource quota (e.g. gpt-4o-mini for the Foundry agent)
  if (m.includes("quota") || (m.includes("no capacity") && m.includes("region"))) {
    return {
      title: "Not enough quota",
      guidance:
        "Your subscription has no quota for a required resource (often an AI model like gpt-4o-mini) in the chosen region. Pick a region where you have quota, or request a quota increase in the Azure/Foundry portal, then retry.",
      retryable: true,
    };
  }

  // Azure resource provider not registered
  if (m.includes("not registered") || m.includes("subscriptionnotregistered")) {
    return {
      title: "Azure resource provider not registered",
      guidance:
        "A required Azure resource provider isn't registered on your subscription (e.g. Microsoft.Storage or Microsoft.Sql). Register it under Subscription → Resource providers in the Azure portal, then retry.",
      retryable: true,
    };
  }

  // Region / subscription provisioning policy restriction
  if (
    (m.includes("restricted") && (m.includes("region") || m.includes("provision"))) ||
    m.includes("not available in this region") ||
    m.includes("disallowed by policy")
  ) {
    return {
      title: "Region blocked for this subscription",
      guidance:
        "Your subscription's policy blocks provisioning in the selected region. Choose a different Azure region and retry.",
      retryable: true,
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

  // Fallback — no specific pattern matched. Show the (coerced, readable) detail
  // so nothing is hidden, with actionable guidance when there's no detail.
  return {
    title: "Deployment failed",
    guidance:
      msg ||
      "An unexpected error occurred. Wait a moment and retry; if it keeps failing, check that your Fabric capacity is active and that you have permissions in the selected Azure subscription.",
    retryable: true,
  };
}

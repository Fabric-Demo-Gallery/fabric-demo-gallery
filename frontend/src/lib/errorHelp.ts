// Maps raw deployment/capacity error strings to friendly, actionable guidance.
// Pattern-matched against the failure modes seen during real Fabric deploys.
// Always falls back to the raw message so no information is ever hidden.

export interface FriendlyError {
  title: string;
  guidance: string;
  /** Whether retrying the same deploy is likely to help. */
  retryable: boolean;
}

export interface AuthError extends FriendlyError {
  /** Stable short code for anonymous telemetry (e.g. "AADSTS65001", "popup_blocked"). */
  code: string;
}

// Classifies Microsoft Entra (AADSTSnnnnn) and MSAL.js (snake_case) sign-in /
// authorization failures into actionable guidance. Returns null when the string
// isn't an auth error so explainError can try its deployment patterns instead.
export function classifyAuthError(raw: string | null | undefined): AuthError | null {
  const msg = (raw ?? "").toString();
  const m = msg.toLowerCase();
  if (!m) return null;

  if (m.includes("aadsts70011") || (m.includes(".default") && m.includes("scope") && m.includes("not valid"))) {
    return {
      code: "AADSTS70011",
      title: "Outdated app version cached",
      guidance:
        "Your browser is running an old cached version of this site. Hard-refresh the page (Ctrl+Shift+R), then click Deploy again.",
      retryable: true,
    };
  }
  if (m.includes("aadsts65001") || m.includes("aadsts90094") || m.includes("consent_required") || m.includes("need admin approval")) {
    return {
      code: "consent_required",
      title: "Admin approval needed",
      guidance:
        "Your organization requires an admin to approve this app's permissions. Use \u201cHow to approve\u201d in the blue banner (or send it to your admin) \u2014 a one-time approval unblocks your whole tenant. Then retry.",
      retryable: false,
    };
  }
  if (m.includes("aadsts53003") || m.includes("conditional access")) {
    return {
      code: "conditional_access",
      title: "Blocked by a Conditional Access policy",
      guidance:
        "Your organization's Conditional Access policy blocked the authorization (device, location, or MFA requirements). Sign in from a compliant device/network, then retry.",
      retryable: false,
    };
  }
  if (m.includes("aadsts50011")) {
    return {
      code: "AADSTS50011",
      title: "Sign-in configuration issue",
      guidance:
        "The sign-in reply URL isn't registered for this site \u2014 a site configuration problem, not something you can fix. Please report it via the GitHub link in the header.",
      retryable: false,
    };
  }
  if (m.includes("aadsts700016")) {
    return {
      code: "AADSTS700016",
      title: "App not available in your organization",
      guidance:
        "This app isn't provisioned in your Microsoft Entra tenant yet. Sign out and sign in again (which registers it), or ask your admin to approve the app, then retry.",
      retryable: true,
    };
  }
  if (/popup_window_error|empty_window_error|monitor_window_timeout/.test(m)) {
    return {
      code: "popup_blocked",
      title: "Sign-in popup blocked",
      guidance:
        "The browser blocked the sign-in popup. Allow popups for this site (look for the blocked-popup icon in the address bar), then click Deploy again.",
      retryable: true,
    };
  }
  if (m.includes("user_cancelled")) {
    return {
      code: "user_cancelled",
      title: "Sign-in popup closed",
      guidance: "The sign-in popup was closed before finishing. Click Deploy again and approve the popup to continue.",
      retryable: true,
    };
  }
  if (m.includes("interaction_in_progress")) {
    return {
      code: "interaction_in_progress",
      title: "Another sign-in window is open",
      guidance: "A sign-in window is still open or didn't finish. Close any sign-in popups, then click Deploy again.",
      retryable: true,
    };
  }
  if (m.includes("interaction_required") || m.includes("login_required") || m.includes("no_account_error")) {
    return {
      code: "interaction_required",
      title: "Quick re-authorization needed",
      guidance: "Your session needs a quick re-authorization. Click Deploy again and approve the sign-in popup.",
      retryable: true,
    };
  }
  if (m.includes("aadsts650052") || m.includes("lacks a service principal") || m.includes("invalid_client")) {
    // The tenant is missing a first-party Microsoft service principal (usually
    // 'Azure Storage' in fresh sandbox tenants) — no consent or retry can fix
    // it; a tenant admin must provision the SP once. Entra surfaces this as
    // error=invalid_client, sometimes WITHOUT the AADSTS650052 description
    // reaching MSAL (seen live 2026-07-24: cryptic invalid_client popup, zero
    // telemetry) — so bare invalid_client maps here too, with Azure Storage as
    // the by-far-most-likely missing service (its token is acquired on every
    // deploy; the other audiences are best-effort and swallowed).
    const is650052 = m.includes("aadsts650052") || m.includes("lacks a service principal");
    const svcId = msg.match(/access a service '([0-9a-fA-F-]{36})'/)?.[1] ?? "e406a681-f3d4-42a8-90b6-c2b029497af1";
    const svcName = (is650052 ? msg.match(/\(([^)]+)\)/)?.[1] : undefined) ?? "Azure Storage";
    return {
      code: is650052 ? "AADSTS650052" : "invalid_client",
      title: `Your organization is missing the '${svcName}' service`,
      guidance:
        `Your Microsoft Entra tenant doesn't have the '${svcName}' service principal, so no sign-in can grant access to it — retrying won't help. A tenant admin must provision it once by running: az ad sp create --id ${svcId} — in Microsoft-internal sandbox tenants (MngEnv…/MCAP…) you are usually that admin: run az login --tenant <your-tenant> --allow-no-subscriptions first, then the command above, then sign out and back in and retry the deploy.`,
      retryable: false,
    };
  }
  if (m.includes("aadsts")) {
    // Any other Entra error \u2014 surface the code so it's diagnosable.
    const codeMatch = msg.match(/AADSTS\d+/i);
    return {
      code: codeMatch ? codeMatch[0].toUpperCase() : "aadsts_other",
      title: "Microsoft Entra sign-in error",
      guidance:
        "Microsoft Entra returned an error during authorization. Click Deploy to try again; if it persists, copy the technical details and report them via the GitHub link.",
      retryable: true,
    };
  }
  return null;
}

export function explainError(raw: string | null | undefined): FriendlyError {
  const msg = (raw ?? "").toString();
  const m = msg.toLowerCase();

  // Sign-in / authorization failures first — the Entra & MSAL codes are precise
  // and must not fall through to the generic 401/permission buckets below.
  const auth = classifyAuthError(msg);
  if (auth) return auth;

  // Fabric IQ (Ontology items, preview) not enabled for the tenant/capacity.
  // The create-ontology notebook fails with a crafted message containing
  // "Fabric IQ". Must precede the generic "feature is not available" bucket,
  // whose 'Users can create Fabric items' guidance is wrong for this case.
  if (m.includes("fabric iq") && (m.includes("not enabled") || m.includes("rejected"))) {
    return {
      title: "Fabric IQ (preview) isn't enabled for this tenant",
      guidance:
        "This scenario creates an Ontology item, which requires Fabric IQ (preview). Ask a Fabric admin to enable Fabric IQ / Ontology (preview) in the Fabric Admin portal (Tenant settings), confirm the capacity's region supports it, then delete the partially-created workspace and redeploy.",
      retryable: false,
    };
  }

  // Fabric items disabled for the tenant/capacity. Workspace creation succeeds
  // (a legacy Power BI operation) but the FIRST Fabric item (lakehouse) is
  // rejected with 403 "The feature is not available" — meaning the tenant
  // setting 'Users can create Fabric items' is off, or the chosen capacity
  // isn't Fabric-enabled (e.g. Premium Per User). Deterministic — retrying
  // can't help until an admin/capacity change. Seen live: colakings.org 4×.
  if (m.includes("feature is not available") || m.includes("featurenotavailable")) {
    return {
      title: "Your organization or capacity doesn't allow Fabric items",
      guidance:
        "The workspace was created, but creating Fabric items (lakehouses, notebooks) was rejected by your tenant. Two common causes: (1) a Fabric admin needs to enable \u201cUsers can create Fabric items\u201d in the Fabric Admin portal \u2192 Tenant settings (or add you to its allowed security group); (2) the capacity you selected isn't Fabric-enabled \u2014 Premium Per User doesn't support Fabric items; pick an F-SKU capacity or start a free Fabric trial (app.fabric.microsoft.com \u2192 account menu \u2192 Start trial), then retry.",
      retryable: false,
    };
  }

  // Stale consent: the signed-in token was granted before the app added a newer
  // permission (seen live 3x after the Item.Execute.All regression). Must be
  // checked BEFORE the generic 403 bucket, whose "ask your Fabric admin"
  // guidance is wrong for this — a fresh sign-in fixes it, an admin can't.
  if (m.includes("sufficient scopes")) {
    return {
      title: "App permissions out of date",
      guidance:
        "Your sign-in was authorized before this app added a newer permission it now needs. Hard-refresh the page (Ctrl+Shift+R), sign out (top right), sign back in and approve the popup \u2014 that refreshes the app's permissions \u2014 then retry the deploy.",
      retryable: true,
    };
  }

  // Azure SQL blocked by a subscription policy (common in Microsoft sandbox
  // tenants: the MCAPS 'SFI' policy flips public network access off at server
  // creation). Must be checked BEFORE the 403 and network buckets — the 400
  // variant contains the word "network" and would misclassify as a transient
  // "Network hiccup", and retrying can never fix a policy.
  if (m.includes("sql") && (m.includes("public network") || m.includes("firewall rules"))) {
    return {
      title: "Subscription policy blocks SQL public access",
      guidance:
        "Your Azure subscription has a policy (standard in Microsoft sandbox/MCAPS subscriptions) that disables public network access on new SQL servers, which this demo needs. Fix: deploy again with a NEW resource group name \u2014 the app tags new resource groups with SecurityControl=Ignore, which exempts them from the policy. For an existing resource group, tag it yourself: az tag update --resource-id /subscriptions/<sub-id>/resourceGroups/<rg-name> --operation merge --tags SecurityControl=Ignore \u2014 then retry.",
      retryable: true,
    };
  }

  // Deploy watchdog 504: notebooks ran past the allowed window. The workspace
  // and items exist and notebook jobs may still finish server-side.
  if (m.includes("504") || m.includes("didn't finish in time") || m.includes("did not finish in time")) {
    return {
      title: "Deployment timed out while notebooks were running",
      guidance:
        "The workspace and all items were created, but the data-loading notebooks ran past the allowed time \u2014 usually a slow/busy capacity. The notebook jobs may still finish on their own: open the workspace in Fabric and check the notebook run status in ~10\u201315 minutes. If data or reports look incomplete after that, delete the workspace and redeploy on a less busy capacity.",
      retryable: true,
    };
  }

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

  // Rate limit (the backend allows 20 deploys/hour per client)
  if (m.includes("429") || m.includes("rate limit") || m.includes("too many requests")) {
    return {
      title: "Slow down a moment",
      guidance:
        "You've hit the deployment rate limit (20 per hour). Wait a few minutes and try again — existing deployments keep running.",
      retryable: true,
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

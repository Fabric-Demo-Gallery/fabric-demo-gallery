# Pre-demo checklist

A 5-minute manual smoke test to run before presenting from the Fabric Demo Gallery.
Catches the environment problems that automated checks can't (paused capacity, expired
sign-in, a sector that hasn't been deployed recently).

## 1. Environment
- [ ] Fabric **capacity is Active** (not paused). The deploy now fails fast with a clear
      message if it's paused, but resume it beforehand to avoid surprises.
- [ ] You can **sign in** with the Entra account that has Fabric workspace-create rights.
- [ ] Production backend is healthy: `GET https://fabric-demo-gallery-api.azurewebsites.net/api/health`
      returns `{"status":"ok"}`.

## 2. Specs (run locally, takes seconds)
- [ ] `python tools/validate_mirroring_specs.py` → **12/12 specs valid** and
      **Scenario wiring OK**.

## 3. One end-to-end deploy (per scenario type you plan to show)
- [ ] Open the demo, pick the scenario, choose the capacity (and Azure subscription +
      resource group for mirroring / shortcut scenarios). The **Deploy button stays disabled**
      until those are set.
- [ ] Click Deploy and watch the live steps stream. Each step shows green (completed),
      grey (skipped, non-critical), or red (failed, with the reason inline).
- [ ] For **mirroring**: confirm `mirror-sync` reports tables replicating, then open the
      `02_live_change` notebook and run it to show a source change appear in OneLake.
- [ ] **Delete the workspace** afterward (button on the success card). For mirroring this
      also removes the Azure SQL server.

## 4. Failure handling (optional sanity check)
- [ ] If a deploy fails, the error card shows a friendly title + guidance, and partially
      created resources (workspace, and any Azure SQL server) are **torn down automatically**.
      The message names anything that couldn't be auto-removed.

## Notes
- Live-testing every sector takes ~10 min each; the metadata engine is shared, so smoke-
  testing one mirroring sector + one standard sector is usually enough confidence.
- A transient network blip during a deploy is tolerated (idempotent GETs retry, long polls
  keep going). If the network is genuinely down, the deploy fails cleanly and cleans up.

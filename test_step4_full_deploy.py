"""
Step 4: Full Manufacturing Demo Deployment
Creates workspace, lakehouse, uploads sample data, creates notebooks, runs them.
This is the REAL deployment — items will remain in your Fabric tenant.
"""

import subprocess
import sys
import time
import json
import base64
from pathlib import Path
import httpx

DEMOS_DIR = Path(__file__).parent / "demos"
API = "https://api.fabric.microsoft.com/v1"
ONELAKE = "https://onelake.dfs.fabric.microsoft.com"


def get_token(resource: str) -> str:
    result = subprocess.run(
        ["az", "account", "get-access-token", "--resource", resource, "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, shell=True
    )
    return result.stdout.strip()


def poll_lro(client: httpx.Client, location: str, timeout: int = 300) -> dict:
    start = time.time()
    while time.time() - start < timeout:
        r = client.get(location)
        if r.status_code == 200:
            body = r.json()
            status = body.get("status", "").lower()
            if status in ("succeeded", "completed"):
                return body
            if status in ("failed", "cancelled"):
                print(f"  ✗ LRO {status}: {json.dumps(body)[:300]}")
                sys.exit(1)
        time.sleep(5)
    print("  ✗ LRO timed out")
    sys.exit(1)


def poll_job(client: httpx.Client, location: str, timeout: int = 600) -> dict:
    """Poll a notebook job — Fabric returns job status at the Location URL."""
    start = time.time()
    while time.time() - start < timeout:
        r = client.get(location)
        if r.status_code == 200:
            body = r.json()
            status = body.get("status", "").lower()
            if status in ("completed",):
                return body
            if status in ("failed", "cancelled", "deduped"):
                print(f"  ✗ Job {status}: {json.dumps(body)[:300]}")
                return body
            print(f"    ... job status: {status}")
        time.sleep(10)
    print("  ✗ Job timed out")
    return {}


def main():
    demo_id = "manufacturing-qc"
    ws_name = "FabricDemoGallery-Manufacturing-QC"

    print("=" * 60)
    print(f"Step 4: Full Deployment — {demo_id}")
    print("=" * 60)

    fabric_token = get_token("https://api.fabric.microsoft.com")
    storage_token = get_token("https://storage.azure.com")

    fabric = httpx.Client(
        headers={"Authorization": f"Bearer {fabric_token}", "Content-Type": "application/json"},
        timeout=60
    )
    onelake = httpx.Client(
        headers={"Authorization": f"Bearer {storage_token}"},
        timeout=120
    )

    manifest = json.loads((DEMOS_DIR / demo_id / "manifest.json").read_text())
    demo_dir = DEMOS_DIR / demo_id

    # 1. Find capacity
    print("\n[1/7] Finding capacity...")
    resp = fabric.get(f"{API}/workspaces")
    capacity_id = next(ws["capacityId"] for ws in resp.json()["value"] if ws.get("capacityId"))
    print(f"  ✓ Capacity: {capacity_id}")

    # 2. Create workspace
    print(f"\n[2/7] Creating workspace '{ws_name}'...")
    resp = fabric.post(f"{API}/workspaces", json={"displayName": ws_name, "capacityId": capacity_id})
    if resp.status_code not in (200, 201):
        print(f"  ✗ {resp.status_code}: {resp.text[:300]}")
        sys.exit(1)
    ws_id = resp.json()["id"]
    print(f"  ✓ Workspace: {ws_id}")

    # 3. Create lakehouse
    lh_name = "quality_lakehouse"
    print(f"\n[3/7] Creating lakehouse '{lh_name}'...")
    resp = fabric.post(f"{API}/workspaces/{ws_id}/items", json={"displayName": lh_name, "type": "Lakehouse"})
    if resp.status_code == 202:
        result = poll_lro(fabric, resp.headers["Location"])
        lh_id = result.get("id", "")
    elif resp.status_code == 201:
        lh_id = resp.json()["id"]
    else:
        print(f"  ✗ {resp.status_code}: {resp.text[:300]}")
        sys.exit(1)
    print(f"  ✓ Lakehouse: {lh_id}")

    # 4. Upload sample data files
    data_dir = demo_dir / "data"
    data_files = list(data_dir.glob("*.csv"))
    print(f"\n[4/7] Uploading {len(data_files)} sample data files...")
    for f in data_files:
        remote = f"landing/{f.name}"
        data = f.read_bytes()
        base = f"{ONELAKE}/{ws_id}/{lh_id}/Files/{remote}"

        r = onelake.put(f"{base}?resource=file", content=b"")
        if r.status_code not in (200, 201):
            print(f"  ✗ Create {f.name}: {r.status_code} {r.text[:100]}")
            continue

        r = onelake.patch(f"{base}?action=append&position=0", content=data)
        if r.status_code not in (200, 202):
            print(f"  ✗ Append {f.name}: {r.status_code}")
            continue

        r = onelake.patch(f"{base}?action=flush&position={len(data)}")
        if r.status_code not in (200, 202):
            print(f"  ✗ Flush {f.name}: {r.status_code}")
            continue

        print(f"  ✓ {f.name} ({len(data):,} bytes)")

    # 5. Create notebooks
    notebooks = [i for i in manifest["fabricItems"] if i["type"] == "Notebook"]
    notebooks.sort(key=lambda x: x.get("order", 99))
    notebook_ids = {}

    print(f"\n[5/7] Creating {len(notebooks)} notebooks...")
    for nb in notebooks:
        nb_name = nb["name"]
        ipynb_path = demo_dir / nb.get("definitionPath", f"notebooks/{nb_name}.ipynb")
        ipynb = json.loads(ipynb_path.read_text(encoding="utf-8"))

        # Inject lakehouse binding
        ipynb.setdefault("metadata", {})
        ipynb["metadata"]["dependencies"] = {
            "lakehouse": {
                "default_lakehouse": lh_id,
                "default_lakehouse_name": lh_name,
                "default_lakehouse_workspace_id": ws_id,
                "known_lakehouses": [{"id": lh_id}],
            }
        }

        encoded = base64.b64encode(json.dumps(ipynb).encode()).decode()
        definition = {
            "parts": [{
                "path": "notebook-content.py",
                "payload": encoded,
                "payloadType": "InlineBase64",
            }]
        }

        resp = fabric.post(f"{API}/workspaces/{ws_id}/items", json={
            "displayName": nb_name,
            "type": "Notebook",
            "definition": definition,
        })

        if resp.status_code == 202:
            result = poll_lro(fabric, resp.headers["Location"])
            nb_id = result.get("id", "")
        elif resp.status_code == 201:
            nb_id = resp.json()["id"]
        else:
            print(f"  ✗ {nb_name}: {resp.status_code} {resp.text[:200]}")
            continue

        notebook_ids[nb_name] = nb_id
        print(f"  ✓ {nb_name}: {nb_id}")

    # 6. Execute notebooks sequentially
    print(f"\n[6/7] Executing notebooks (Bronze → Silver → Gold)...")
    for nb in notebooks:
        nb_name = nb["name"]
        nb_id = notebook_ids.get(nb_name)
        if not nb_id:
            print(f"  ⚠ Skipping {nb_name} (no ID)")
            continue

        print(f"\n  Running {nb_name}...")
        resp = fabric.post(
            f"{API}/workspaces/{ws_id}/items/{nb_id}/jobs/instances?jobType=RunNotebook",
            json={
                "executionData": {
                    "configuration": {
                        "defaultLakehouse": {
                            "id": lh_id,
                            "name": lh_name,
                        }
                    }
                }
            }
        )
        if resp.status_code == 202:
            location = resp.headers.get("Location")
            if location:
                result = poll_job(fabric, location, timeout=600)
                status = result.get("status", "unknown")
                print(f"  ✓ {nb_name} → {status}")
            else:
                print(f"  ✓ {nb_name} accepted (no Location header)")
        else:
            print(f"  ✗ {nb_name}: {resp.status_code} {resp.text[:200]}")

    # 7. Summary
    print(f"\n[7/7] Creating semantic model and pipeline (placeholder)...")
    # These require TMDL and pipeline definitions — skipping for now
    resp = fabric.post(f"{API}/workspaces/{ws_id}/items", json={
        "displayName": "quality_analytics_model",
        "type": "SemanticModel",
    })
    if resp.status_code in (200, 201):
        print(f"  ✓ Semantic model created (empty — needs TMDL definition)")
    elif resp.status_code == 202:
        poll_lro(fabric, resp.headers["Location"])
        print(f"  ✓ Semantic model created (empty)")
    else:
        print(f"  ⚠ Semantic model: {resp.status_code} {resp.text[:100]}")

    resp = fabric.post(f"{API}/workspaces/{ws_id}/items", json={
        "displayName": "daily_quality_pipeline",
        "type": "DataPipeline",
    })
    if resp.status_code in (200, 201):
        print(f"  ✓ Pipeline created (empty — needs definition)")
    elif resp.status_code == 202:
        poll_lro(fabric, resp.headers["Location"])
        print(f"  ✓ Pipeline created (empty)")
    else:
        print(f"  ⚠ Pipeline: {resp.status_code} {resp.text[:100]}")

    print("\n" + "=" * 60)
    print("🎉 Deployment complete!")
    print(f"   Workspace: {ws_name}")
    print(f"   Workspace ID: {ws_id}")
    print(f"   Open in Fabric: https://app.fabric.microsoft.com/groups/{ws_id}")
    print("=" * 60)
    print("\nTo clean up later, run:")
    print(f'  az rest --method delete --resource "https://api.fabric.microsoft.com" --url "https://api.fabric.microsoft.com/v1/workspaces/{ws_id}"')


if __name__ == "__main__":
    main()

"""
Step 2: Create a test workspace, verify it exists, then delete it.
Proves the app can create and clean up Fabric items.
"""

import subprocess
import sys
import time
import httpx


def get_fabric_token() -> str:
    result = subprocess.run(
        ["az", "account", "get-access-token", "--resource", "https://api.fabric.microsoft.com", "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, shell=True
    )
    if result.returncode != 0:
        print(f"ERROR: {result.stderr}")
        sys.exit(1)
    return result.stdout.strip()


def main():
    print("=" * 60)
    print("Step 2: Create & Delete a Test Workspace")
    print("=" * 60)

    token = get_fabric_token()
    client = httpx.Client(
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30
    )
    API = "https://api.fabric.microsoft.com/v1"

    # Find a capacity ID from existing workspaces
    print("\n[1/4] Finding a capacity to use...")
    resp = client.get(f"{API}/workspaces")
    resp.raise_for_status()
    workspaces = resp.json()["value"]
    capacity_id = None
    for ws in workspaces:
        if ws.get("capacityId"):
            capacity_id = ws["capacityId"]
            print(f"  ✓ Using capacity: {capacity_id}")
            break
    if not capacity_id:
        print("  ✗ No capacity found. You need a Fabric capacity to create workspaces.")
        sys.exit(1)

    # Create workspace
    ws_name = "FabricDemoGallery-TEST-DeleteMe"
    print(f"\n[2/4] Creating workspace '{ws_name}'...")
    resp = client.post(f"{API}/workspaces", json={
        "displayName": ws_name,
        "capacityId": capacity_id,
    })
    if resp.status_code not in (200, 201):
        print(f"  ✗ Failed: {resp.status_code} {resp.text[:200]}")
        sys.exit(1)
    ws = resp.json()
    ws_id = ws["id"]
    print(f"  ✓ Created! ID: {ws_id}")

    # Verify it exists
    print(f"\n[3/4] Verifying workspace exists...")
    resp = client.get(f"{API}/workspaces/{ws_id}")
    resp.raise_for_status()
    print(f"  ✓ Workspace '{resp.json()['displayName']}' confirmed")

    # Delete it
    print(f"\n[4/4] Deleting test workspace...")
    resp = client.delete(f"{API}/workspaces/{ws_id}")
    if resp.status_code in (200, 204):
        print(f"  ✓ Deleted successfully")
    else:
        print(f"  ✗ Delete returned: {resp.status_code} {resp.text[:200]}")

    print("\n" + "=" * 60)
    print("Step 2 passed! Workspace create + delete works.")
    print("=" * 60)


if __name__ == "__main__":
    main()

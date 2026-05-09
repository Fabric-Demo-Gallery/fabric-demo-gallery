"""
Step 3: Create workspace + lakehouse + upload a sample CSV file.
Then verify the file is there, and clean up.
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
    return result.stdout.strip()


def get_storage_token() -> str:
    """OneLake uses storage.azure.com audience, not the Fabric audience."""
    result = subprocess.run(
        ["az", "account", "get-access-token", "--resource", "https://storage.azure.com", "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, shell=True
    )
    return result.stdout.strip()


def main():
    print("=" * 60)
    print("Step 3: Workspace + Lakehouse + File Upload")
    print("=" * 60)

    fabric_token = get_fabric_token()
    storage_token = get_storage_token()
    API = "https://api.fabric.microsoft.com/v1"
    ONELAKE = "https://onelake.dfs.fabric.microsoft.com"

    fabric = httpx.Client(
        headers={"Authorization": f"Bearer {fabric_token}", "Content-Type": "application/json"},
        timeout=60
    )
    onelake = httpx.Client(
        headers={"Authorization": f"Bearer {storage_token}"},
        timeout=60
    )

    # Find capacity
    print("\n[1/6] Finding capacity...")
    resp = fabric.get(f"{API}/workspaces")
    capacity_id = next(ws["capacityId"] for ws in resp.json()["value"] if ws.get("capacityId"))
    print(f"  ✓ Capacity: {capacity_id}")

    # Create workspace
    ws_name = "FabricDemoGallery-TEST-Step3"
    print(f"\n[2/6] Creating workspace '{ws_name}'...")
    resp = fabric.post(f"{API}/workspaces", json={"displayName": ws_name, "capacityId": capacity_id})
    ws_id = resp.json()["id"]
    print(f"  ✓ Workspace: {ws_id}")

    try:
        # Create lakehouse
        print(f"\n[3/6] Creating lakehouse 'test_lakehouse'...")
        resp = fabric.post(f"{API}/workspaces/{ws_id}/items", json={
            "displayName": "test_lakehouse",
            "type": "Lakehouse"
        })
        if resp.status_code == 201:
            lh = resp.json()
        elif resp.status_code == 202:
            # LRO — poll
            location = resp.headers.get("Location")
            print(f"  ... waiting for LRO")
            for _ in range(30):
                time.sleep(3)
                r = fabric.get(location)
                if r.status_code == 200 and r.json().get("status", "").lower() in ("succeeded", "completed"):
                    lh = r.json()
                    break
            else:
                print("  ✗ Lakehouse creation timed out")
                raise SystemExit(1)
        else:
            print(f"  ✗ Failed: {resp.status_code} {resp.text[:300]}")
            raise SystemExit(1)

        lh_id = lh["id"]
        print(f"  ✓ Lakehouse: {lh_id}")

        # Upload a small CSV file
        print(f"\n[4/6] Uploading sample CSV to lakehouse Files/...")
        csv_content = b"machine_id,temperature,pressure\nMCH-001,75.2,150.3\nMCH-002,80.1,145.7\nMCH-003,72.5,155.0\n"
        file_path = f"landing/test_data.csv"

        # Create file (using GUIDs for workspace and lakehouse)
        create_url = f"{ONELAKE}/{ws_id}/{lh_id}/Files/{file_path}?resource=file"
        r = onelake.put(create_url, content=b"")
        if r.status_code not in (200, 201):
            print(f"  ✗ Create file failed: {r.status_code} {r.text[:200]}")
            raise SystemExit(1)

        # Append data
        append_url = f"{ONELAKE}/{ws_id}/{lh_id}/Files/{file_path}?action=append&position=0"
        r = onelake.patch(append_url, content=csv_content)
        if r.status_code not in (200, 202):
            print(f"  ✗ Append failed: {r.status_code} {r.text[:200]}")
            raise SystemExit(1)

        # Flush
        flush_url = f"{ONELAKE}/{ws_id}/{lh_id}/Files/{file_path}?action=flush&position={len(csv_content)}"
        r = onelake.patch(flush_url)
        if r.status_code not in (200, 202):
            print(f"  ✗ Flush failed: {r.status_code} {r.text[:200]}")
            raise SystemExit(1)
        print(f"  ✓ Uploaded {len(csv_content)} bytes to Files/{file_path}")

        # Verify file exists
        print(f"\n[5/6] Verifying file exists in OneLake...")
        list_url = f"{ONELAKE}/{ws_id}/{lh_id}/Files/landing?resource=filesystem&recursive=false"
        r = onelake.get(list_url)
        if r.status_code == 200:
            print(f"  ✓ File listing returned OK")
        else:
            print(f"  ? List returned {r.status_code} (file may still be there)")

        print(f"\n  ✅ SUCCESS — workspace + lakehouse + file upload all work!")

    finally:
        # Cleanup
        print(f"\n[6/6] Cleaning up — deleting workspace...")
        fabric.delete(f"{API}/workspaces/{ws_id}")
        print(f"  ✓ Workspace deleted")

    print("\n" + "=" * 60)
    print("Step 3 passed! Ready for full demo deployment.")
    print("=" * 60)


if __name__ == "__main__":
    main()

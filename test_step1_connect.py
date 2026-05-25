"""
Step-by-step test: verify each Fabric API operation works.
Run this script to test one operation at a time.
Uses `az` CLI token — no app registration needed.
"""

import subprocess
import json
import sys

def get_fabric_token() -> str:
    """Get a Fabric API token using az CLI."""
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
    print("Fabric Demo Gallery — Step-by-Step Test")
    print("=" * 60)

    # Step 1: Get token
    print("\n[1/2] Getting Fabric API token via az CLI...")
    token = get_fabric_token()
    print(f"  ✓ Token acquired ({len(token)} chars)")

    # Step 2: List workspaces
    print("\n[2/2] Listing your Fabric workspaces...")
    import httpx
    client = httpx.Client(headers={"Authorization": f"Bearer {token}"}, timeout=30)
    resp = client.get("https://api.fabric.microsoft.com/v1/workspaces")
    resp.raise_for_status()
    workspaces = resp.json()["value"]
    print(f"  ✓ Found {len(workspaces)} workspaces:")
    for ws in workspaces[:10]:
        cap = ws.get("capacityId") or "(no capacity)"
        print(f"    - {ws['displayName']}  [capacity: {cap[:8]}...]")

    print("\n" + "=" * 60)
    print("All checks passed! Your Fabric connection works.")
    print("=" * 60)
    print(f"\nToken (save for next steps):\n{token[:50]}...")


if __name__ == "__main__":
    main()

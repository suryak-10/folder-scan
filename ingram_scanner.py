"""
ingram_scanner.py
Job Folder Structure Crawler
Uses macOS mounted SMB share via Finder (no pysmb needed)

Mount your share first:
  Finder → Go → Connect to Server (⌘K) → smb://172.16.100.12/ID-Direct

Then run:
  python3 job_folder_crawler.py

Output: job_structure.json
"""

import json
import os

from folder_scan_utils import crawl_tree, count_nodes

# ─── CONFIG ────────────────────────────────────────────────────────────────────
# Check your mount point with: ls /Volumes/
# Replace "ID-Direct" with whatever appears in /Volumes/
ROOT = "/Volumes/ID-Direct"
OUTPUT_FILE = "job_structure.json"
# ───────────────────────────────────────────────────────────────────────────────


def crawl_job(job_path: str, job_name: str) -> dict | None:
    """
    Inside a job folder (e.g. 142441_COMP_black_IDSPLIT):
      1. Find subfolder ending with _delivery
      2. Inside that, find subfolder starting with 95
      3. Recursively list its contents
    """
    job_node = {"job": job_name, "delivery_folders": []}

    try:
        entries = sorted(os.scandir(job_path), key=lambda e: e.name.lower())
    except Exception as ex:
        print(f"    ⚠️  Cannot read job {job_name}: {ex}")
        return None

    delivery_folders = [
        e for e in entries
        if e.is_dir() and e.name.lower().endswith("_delivery")
    ]

    if not delivery_folders:
        return None  # silently skip jobs with no _delivery folder

    for delivery in delivery_folders:
        print(f"    📦  {delivery.name}")
        delivery_node = {"name": delivery.name, "digital_asset_folders": []}

        try:
            delivery_entries = sorted(os.scandir(delivery.path), key=lambda e: e.name.lower())
        except Exception as ex:
            print(f"      ⚠️  Cannot read delivery folder: {ex}")
            continue

        asset_folders = [
            e for e in delivery_entries
            if e.is_dir() and e.name.startswith("95")
        ]

        if not asset_folders:
            print(f"      ℹ️  No 95_* folder found in {delivery.name}")

        for af in asset_folders:
            print(f"      🗂️   {af.name}")
            contents = crawl_tree(af.path)
            delivery_node["digital_asset_folders"].append({
                "name": af.name,
                "path": af.path,
                "contents": contents,
            })

        job_node["delivery_folders"].append(delivery_node)

    return job_node if job_node["delivery_folders"] else None


def main():
    # Validate mount point
    if not os.path.isdir(ROOT):
        print(f"❌  Mount point not found: {ROOT}")
        print(f"    Please connect via Finder first:")
        print(f"    Go → Connect to Server (⌘K) → smb://172.16.100.12/ID-Direct")
        print(f"\n    Then check your mount point with: ls /Volumes/")
        print(f"    Update ROOT in this script to match.")
        return

    print(f"✅  Share mounted at: {ROOT}")
    print(f"🔍  Scanning...\n")

    result = {
        "share": ROOT,
        "clients": [],
    }

    try:
        client_entries = sorted(os.scandir(ROOT), key=lambda e: e.name.lower())
    except Exception as ex:
        print(f"❌  Cannot read share root: {ex}")
        return

    client_folders = [e for e in client_entries if e.is_dir()]

    for client in client_folders:
        print(f"📁  Client: {client.name}")
        client_node = {"client": client.name, "jobs": []}

        try:
            job_entries = sorted(os.scandir(client.path), key=lambda e: e.name.lower())
        except Exception as ex:
            print(f"  ⚠️  Cannot read client folder: {ex}")
            continue

        for job in job_entries:
            if not job.is_dir():
                continue
            print(f"  🗂️   Job: {job.name}")
            job_node = crawl_job(job.path, job.name)
            if job_node:
                client_node["jobs"].append(job_node)

        result["clients"].append(client_node)

    # Save output
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    # Summary
    total_jobs = sum(len(c["jobs"]) for c in result["clients"])
    total_delivery = sum(
        len(j["delivery_folders"])
        for c in result["clients"]
        for j in c["jobs"]
    )

    print(f"\n✅  Done!")
    print(f"    Clients   : {len(result['clients'])}")
    print(f"    Jobs      : {total_jobs}")
    print(f"    Deliveries: {total_delivery}")
    print(f"    Output    : {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

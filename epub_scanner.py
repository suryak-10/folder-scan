"""
epub_scanner.py
Crawler for the ePub_Server hierarchy.

Walk order:
  /Volumes/ePub_Server
    -> each top-level folder
      -> folders ending with .ePub3
        -> folders ending with WBRT
          -> folders ending with _to
            -> date folders
              -> log every file and folder recursively
"""

import json
import os

from folder_scan_utils import crawl_tree, count_nodes

ROOT = os.getenv("SCAN_ROOT", "/Volumes/ePub_Server")
OUTPUT_FILE = os.getenv("OUTPUT_FILE", "ePub_Server_structure.json")


def list_dirs(path: str, suffix: str | None = None) -> list:
    """Return child directories, optionally filtered by a name suffix."""
    try:
        entries = sorted(os.scandir(path), key=lambda e: e.name.lower())
    except Exception as ex:
        print(f"⚠️  Cannot read {path}: {ex}")
        return []

    folders = [e for e in entries if e.is_dir()]
    if suffix is None:
        return folders
    return [e for e in folders if e.name.lower().endswith(suffix.lower())]


def build_to_node(to_dir) -> dict:
    """Build a tree node for a *_to folder, including each date folder beneath it."""
    to_node = {
        "name": to_dir.name,
        "path": to_dir.path,
        "date_folders": [],
    }

    date_folders = list_dirs(to_dir.path)
    if not date_folders:
        print(f"      ℹ️  No date folders found in {to_dir.name}")

    for date_folder in date_folders:
        print(f"      📅  {date_folder.name}")
        to_node["date_folders"].append({
            "name": date_folder.name,
            "path": date_folder.path,
            "contents": crawl_tree(date_folder.path),
        })

    return to_node


def main():
    if not os.path.isdir(ROOT):
        print(f"❌  Mount point not found: {ROOT}")
        print("    Please connect via Finder first:")
        print("    Go → Connect to Server (⌘K) → smb://172.16.100.50/ePub_Server")
        print("\n    Then check your mount point with: ls /Volumes/")
        print("    Update ROOT in this script or set SCAN_ROOT to match.")
        return

    print(f"✅  Share mounted at: {ROOT}")
    print("🔍  Scanning...\n")

    result = {
        "share": ROOT,
        "top_level_folders": [],
    }

    top_level_folders = list_dirs(ROOT)
    for top in top_level_folders:
        print(f"📁  {top.name}")
        top_node = {
            "name": top.name,
            "path": top.path,
            "epub3_folders": [],
        }

        epub3_folders = list_dirs(top.path, suffix=".ePub3")
        if not epub3_folders:
            print(f"  ℹ️  No .ePub3 folder found in {top.name}")

        for epub3 in epub3_folders:
            print(f"  📘  {epub3.name}")
            epub3_node = {
                "name": epub3.name,
                "path": epub3.path,
                "wbrt_folders": [],
            }

            wbrt_folders = list_dirs(epub3.path, suffix="WBRT")
            if not wbrt_folders:
                print(f"    ℹ️  No WBRT folder found in {epub3.name}")

            for wbrt in wbrt_folders:
                print(f"    📦  {wbrt.name}")
                wbrt_node = {
                    "name": wbrt.name,
                    "path": wbrt.path,
                    "to_folders": [],
                }

                to_folders = list_dirs(wbrt.path, suffix="_to")
                if not to_folders:
                    print(f"      ℹ️  No _to folder found in {wbrt.name}")

                for to_dir in to_folders:
                    print(f"      🗂️  {to_dir.name}")
                    wbrt_node["to_folders"].append(build_to_node(to_dir))

                epub3_node["wbrt_folders"].append(wbrt_node)

            top_node["epub3_folders"].append(epub3_node)

        result["top_level_folders"].append(top_node)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    total_folders = 0
    total_files = 0
    for top in result["top_level_folders"]:
        for epub3 in top["epub3_folders"]:
            for wbrt in epub3["wbrt_folders"]:
                for to_dir in wbrt["to_folders"]:
                    for date_folder in to_dir["date_folders"]:
                        folders, files = count_nodes(date_folder["contents"])
                        total_folders += folders
                        total_files += files

    print("\n✅  Done!")
    print(f"    Top folders : {len(result['top_level_folders'])}")
    print(f"    Folders     : {total_folders}")
    print(f"    Files       : {total_files}")
    print(f"    Output      : {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

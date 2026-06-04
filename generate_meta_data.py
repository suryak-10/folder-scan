"""
=============================================================================
ePub Upload Metadata Report Generator
=============================================================================

Purpose:
    Reads generated metadata JSON files from ./output and generates
    analytical reports about:

    - Prefix project counts
    - Normalized target names
    - Target occurrence counts
    - File naming patterns
    - File pattern occurrence counts

Output:
    ./reports/upload_patterns_report.json

Run:
    python3 generate_report.py
=============================================================================
"""

import json
import re
from collections import defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

INPUT_PATH = Path("./output")
REPORT_PATH = Path("./reports")
REPORT_FILE = REPORT_PATH / "upload_patterns_report.json"

# ---------------------------------------------------------------------------
# Filename normalization
# ---------------------------------------------------------------------------

def normalize_filename(filename: str) -> str:
    """
    Normalize filenames into reusable patterns.

    Examples:
        9781429960304_EPUB.epub
        -> \\d+_EPUB.epub

        141870_cover.jpg
        -> \\d+_cover.jpg
    """

    normalized = re.sub(r"\d+", r"\\d+", filename)

    return normalized


# ---------------------------------------------------------------------------
# Target name normalization
# ---------------------------------------------------------------------------

def normalize_target_name(target_name: str) -> str:
    """
    Normalize target folder names.

    Examples:
        104521_FYI   -> \\d+_FYI
        104521_ePub  -> \\d+_ePub
        1            -> \\d+
    """

    normalized = re.sub(r"\d+", r"\\d+", target_name)

    return normalized


# ---------------------------------------------------------------------------
# Recursive file collector
# ---------------------------------------------------------------------------

def collect_files(node: dict, files: list):
    """
    Recursively collect file names from tree structure.
    """

    if node["type"] == "file":
        files.append(node["name"])
        return

    for child in node.get("children", []):
        collect_files(child, files)


# ---------------------------------------------------------------------------
# Process individual JSON file
# ---------------------------------------------------------------------------

def process_prefix_json(json_file: Path) -> dict:

    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    prefix_name = f"{data['prefixNo']}_{data['prefixName']}"

    report = {
        "prefix": prefix_name,
        "projectCount": len(data.get("projects", [])),
        "targetNames": [],
        "targets": {}
    }

    target_names_set = set()

    # -----------------------------------------------------------------------
    # Traverse projects
    # -----------------------------------------------------------------------

    for project in data.get("projects", []):

        for date_folder in project.get("dateFolders", []):

            for upload_target in date_folder.get("uploadTargets", []):

                raw_target_name = upload_target["targetName"]

                target_name = normalize_target_name(raw_target_name)

                target_names_set.add(target_name)

                # -----------------------------------------------------------
                # Initialize target bucket
                # -----------------------------------------------------------

                if target_name not in report["targets"]:
                    report["targets"][target_name] = {
                        "occurrenceCount": 0,
                        "filePatterns": defaultdict(int)
                    }

                # Count target occurrence
                report["targets"][target_name]["occurrenceCount"] += 1

                # -----------------------------------------------------------
                # Collect files
                # -----------------------------------------------------------

                all_files = []

                for content in upload_target.get("contents", []):
                    collect_files(content, all_files)

                # -----------------------------------------------------------
                # Normalize filenames and count patterns
                # -----------------------------------------------------------

                for filename in all_files:

                    pattern = normalize_filename(filename)

                    report["targets"][target_name]["filePatterns"][pattern] += 1

    # -----------------------------------------------------------------------
    # Convert set -> sorted list
    # -----------------------------------------------------------------------

    report["targetNames"] = sorted(list(target_names_set))

    # -----------------------------------------------------------------------
    # Convert defaultdict -> normal dict
    # -----------------------------------------------------------------------

    for target_name in report["targets"]:

        report["targets"][target_name]["filePatterns"] = dict(
            sorted(
                report["targets"][target_name]["filePatterns"].items(),
                key=lambda x: x[1],
                reverse=True
            )
        )

    return report


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():

    REPORT_PATH.mkdir(parents=True, exist_ok=True)

    final_report = {
        "summary": {
            "totalPrefixes": 0,
            "totalProjects": 0
        },
        "prefixes": []
    }

    json_files = sorted(INPUT_PATH.glob("*.json"))

    if not json_files:
        print("No JSON files found in ./output")
        return

    # -----------------------------------------------------------------------
    # Process all prefix JSON files
    # -----------------------------------------------------------------------

    for json_file in json_files:

        print(f"Processing: {json_file.name}")

        report = process_prefix_json(json_file)

        final_report["prefixes"].append(report)

        final_report["summary"]["totalPrefixes"] += 1
        final_report["summary"]["totalProjects"] += report["projectCount"]

    # -----------------------------------------------------------------------
    # Write final report
    # -----------------------------------------------------------------------

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(final_report, f, indent=2, ensure_ascii=False)

    print("")
    print("=" * 60)
    print("REPORT GENERATED SUCCESSFULLY")
    print(f"Output File: {REPORT_FILE}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()
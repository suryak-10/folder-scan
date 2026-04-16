import json
import re
from collections import defaultdict, Counter

INPUT_FILE = "ingram_job_structure.json"

IGNORE_FILES = {".DS_Store"}


# -----------------------------
# Convert filename → pattern
# -----------------------------
def filename_to_pattern(filename: str) -> str:
    name, ext = re.match(r"^(.*?)(\.[^.]+)?$", filename).groups()

    # Escape regex chars
    name = re.escape(name)

    # Replace digits → \d+
    name = re.sub(r"\d+", r"\\d+", name)

    # Normalize epub variants
    name = re.sub(r"(epub\\d*)", r"EPUB\\d*", name, flags=re.IGNORECASE)

    # Collapse repeated \d+
    name = re.sub(r"(\\d\+)+", r"\\d+", name)

    ext = re.escape(ext or "")

    return f"{name}{ext}"


# -----------------------------
# Convert folder → pattern
# -----------------------------
def folder_to_pattern(folder_name: str) -> str:
    name = re.escape(folder_name)
    name = re.sub(r"\d+", r"\\d+", name)
    return name


# -----------------------------
# Recursive traversal of contents
# -----------------------------
def traverse_contents(contents, prefix, prefix_patterns, global_patterns, special_cases, path=""):
    for item in contents:
        name = item.get("name", "")
        item_type = item.get("type")

        if name in IGNORE_FILES:
            continue

        current_path = f"{path}/{name}" if path else name

        if item_type == "file":
            pattern = filename_to_pattern(name)

            prefix_patterns[prefix][pattern] += 1
            global_patterns[pattern] += 1

            if global_patterns[pattern] < 3:
                special_cases[prefix].append(f"{current_path} -> {pattern}")

        elif item_type == "folder":
            folder_pattern = folder_to_pattern(name)

            prefix_patterns[prefix][f"FOLDER::{folder_pattern}"] += 1
            global_patterns[f"FOLDER::{folder_pattern}"] += 1

            children = item.get("children", [])
            traverse_contents(children, prefix, prefix_patterns, global_patterns, special_cases, current_path)


# -----------------------------
# Main analysis
# -----------------------------
def analyze_json(data):
    prefix_patterns = defaultdict(Counter)
    global_patterns = Counter()
    special_cases = defaultdict(list)

    for client in data.get("clients", []):
        prefix = client.get("client")

        # Skip hidden/system folders
        if prefix.startswith("."):
            continue

        for job in client.get("jobs", []):
            for delivery in job.get("delivery_folders", []):
                for daf in delivery.get("digital_asset_folders", []):

                    # Only process 95_digital_assets
                    if daf.get("name") != "95_digital_assets":
                        continue

                    contents = daf.get("contents", [])

                    traverse_contents(
                        contents,
                        prefix,
                        prefix_patterns,
                        global_patterns,
                        special_cases
                    )

    return prefix_patterns, global_patterns, special_cases


# -----------------------------
# Print report
# -----------------------------
def print_report(prefix_patterns, global_patterns, special_cases):
    print("\n=== COMMON PATTERNS (GLOBAL) ===")
    for pattern, count in global_patterns.most_common(30):
        print(f"{pattern}: {count}")

    print("\n=== PREFIX PATTERNS ===")
    for prefix, counter in prefix_patterns.items():
        print(f"\n-- {prefix} --")
        for pattern, count in counter.most_common(10):
            print(f"{pattern}: {count}")

    print("\n=== SPECIAL / RARE CASES ===")
    for prefix, cases in special_cases.items():
        if cases:
            print(f"\n-- {prefix} --")
            for c in cases[:10]:
                print(c)


# -----------------------------
# MAIN
# -----------------------------
if __name__ == "__main__":
    with open(INPUT_FILE, "r") as f:
        data = json.load(f)

    prefix_patterns, global_patterns, special_cases = analyze_json(data)
    print_report(prefix_patterns, global_patterns, special_cases)
"""
=============================================================================
ID-Direct Server Upload Folder Metadata Collector
=============================================================================

Purpose:
    Recursively scans a network shared drive (ID-Direct) and collects
    structured metadata about uploaded files and folders.

Folder Structure:
    {BASE_PATH}/{prefix_folder}/{job_folder}/{delivery_folder}/{digital_assets_folder}/
        {date_folder}/{upload_target_folder}/[files & subfolders]

    Levels:
        prefix_folder           — e.g. 711_blue_360            (\d+_.+)
        job_folder              — e.g. 152668_COMP_black        (\d+.+)
        delivery_folder         — e.g. 152668_delivery          (ends with _delivery)
        digital_assets_folder   — e.g. 95_digital_assets        (ends with _digital_assets)
        date_folder             — e.g. 01_06.02.2026            (any folder name)
        upload_target_folder    — e.g. To_Client                (any folder name)
        files/subfolders        — collected recursively

How to Run:
    1. Mount your network share, e.g.:
          smb://172.16.100.12/ID-Direct  →  /Volumes/ID-Direct
    2. Adjust BASE_PATH below if your mount point differs.
    3. Run:
          python3 scan_id_direct.py
    4. JSON output files are written to ./output/<prefix_folder>.json

Requirements:
    Python 3.8+  (no third-party packages needed)
=============================================================================
"""

import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Generator, Optional

# ---------------------------------------------------------------------------
# Configurable constants
# ---------------------------------------------------------------------------

BASE_PATH: Path = Path("/Volumes/ID-Direct")
OUTPUT_PATH: Path = Path("./output")

# ---------------------------------------------------------------------------
# Regex patterns
# Only the top two levels are pattern-gated; everything below is open.
# ---------------------------------------------------------------------------

RE_PREFIX_FOLDER         = re.compile(r"^\d+_.+$")
RE_JOB_FOLDER            = re.compile(r"^\d+.+$")
RE_DELIVERY_FOLDER       = re.compile(r"^.+_delivery$",        re.IGNORECASE)
RE_DIGITAL_ASSETS_FOLDER = re.compile(r"^.+_digital_assets$",  re.IGNORECASE)

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Summary counters
# ---------------------------------------------------------------------------

summary: dict = {
    "prefixes_scanned":       0,
    "jobs_scanned":           0,
    "upload_folders_scanned": 0,
    "files_collected":        0,
}

# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _fmt_ts(ts: float) -> str:
    """Convert a POSIX timestamp to an ISO-8601 string."""
    return datetime.fromtimestamp(ts).isoformat()


def _stat_safe(path: Path) -> Optional[dict]:
    """Return a dict with ctime/mtime for *path*, or None on error."""
    try:
        s = path.stat()
        return {"created": _fmt_ts(s.st_ctime), "modified": _fmt_ts(s.st_mtime)}
    except OSError as exc:
        log.warning("Cannot stat %s: %s", path, exc)
        return None


def _iter_dirs(parent: Path, pattern: Optional[re.Pattern] = None) -> Generator[Path, None, None]:
    """
    Yield immediate child directories of *parent*.
    If *pattern* is given, only yield dirs whose names match it.
    Skips inaccessible directories silently (logs a warning).
    """
    try:
        for child in sorted(parent.iterdir(), key=lambda p: p.name.lower()):
            if child.is_dir():
                if pattern is None or pattern.match(child.name):
                    yield child
    except PermissionError as exc:
        log.warning("Cannot access directory %s: %s", parent, exc)
    except OSError as exc:
        log.warning("OS error iterating %s: %s", parent, exc)


def _find_first_dir(parent: Path, pattern: re.Pattern) -> Optional[Path]:
    """Return the first matching child directory, or None."""
    return next(_iter_dirs(parent, pattern), None)


# ---------------------------------------------------------------------------
# Tree builder  (unchanged from original design)
# ---------------------------------------------------------------------------


def build_tree_node(path: Path, base: Path) -> dict:
    """
    Recursively build a tree node for *path*.

    File node  → type/name/extension/absolutePath/relativePath/fileSize/created/modified
    Folder node → type/name/absolutePath/relativePath/created/modified/children[]
    Children are sorted: folders first, then files, each group alphabetically.
    """
    stat     = _stat_safe(path)
    created  = stat["created"]  if stat else None
    modified = stat["modified"] if stat else None

    if path.is_file():
        size: Optional[int] = None
        try:
            size = path.stat().st_size
        except OSError:
            pass
        summary["files_collected"] += 1
        return {
            "type":         "file",
            "name":         path.name,
            "extension":    path.suffix,
            "absolutePath": str(path.resolve()),
            "relativePath": str(path.relative_to(base)),
            "fileSize":     size,
            "created":      created,
            "modified":     modified,
        }

    # --- directory node ---
    children: list[dict] = []
    try:
        entries = sorted(
            path.iterdir(),
            key=lambda p: (p.is_file(), p.name.lower()),
        )
        for entry in entries:
            children.append(build_tree_node(entry, base))
    except PermissionError as exc:
        log.warning("Permission denied reading dir %s: %s", path, exc)
    except OSError as exc:
        log.warning("OS error reading dir %s: %s", path, exc)

    return {
        "type":         "folder",
        "name":         path.name,
        "absolutePath": str(path.resolve()),
        "relativePath": str(path.relative_to(base)),
        "created":      created,
        "modified":     modified,
        "children":     children,
    }


# ---------------------------------------------------------------------------
# Core scanning logic
# ---------------------------------------------------------------------------


def scan_upload_targets(date_dir: Path, base: Path) -> list[dict]:
    """
    Iterate every subfolder inside a date folder (e.g. To_Client, To_Press …).
    No name filtering — whatever folder exists is an upload target.
    Returns a list of uploadTarget dicts.
    """
    targets: list[dict] = []

    for target_dir in _iter_dirs(date_dir):          # no pattern — accept all
        log.info("        Upload target: %s", target_dir.name)
        summary["upload_folders_scanned"] += 1

        contents: list[dict] = []
        try:
            entries = sorted(
                target_dir.iterdir(),
                key=lambda p: (p.is_file(), p.name.lower()),
            )
            for entry in entries:
                contents.append(build_tree_node(entry, base))
        except (PermissionError, OSError) as exc:
            log.warning("Cannot read target dir %s: %s", target_dir, exc)

        targets.append({
            "targetName": target_dir.name,
            "contents":   contents,
        })

    return targets


def scan_digital_assets(digital_assets_dir: Path, base: Path) -> list[dict]:
    """
    Iterate every subfolder inside *_digital_assets (the date folders).
    No name filtering — accept any folder name.
    Returns a list of dateFolder dicts.
    """
    date_folders: list[dict] = []

    for date_dir in _iter_dirs(digital_assets_dir):  # no pattern — accept all
        log.info("      Date folder: %s", date_dir.name)
        upload_targets = scan_upload_targets(date_dir, base)
        if upload_targets:
            date_folders.append({
                "sequenceFolder": date_dir.name,
                "uploadTargets":  upload_targets,
            })

    return date_folders


def scan_job(job_dir: Path, base: Path) -> Optional[dict]:
    """
    Scan a single job folder:
        job_dir  →  *_delivery  →  *_digital_assets  →  date folders

    Returns a job dict, or None if required sub-structure is missing.
    """
    delivery_dir = _find_first_dir(job_dir, RE_DELIVERY_FOLDER)
    if delivery_dir is None:
        log.warning("  No *_delivery folder in %s — skipping", job_dir)
        return None

    digital_assets_dir = _find_first_dir(delivery_dir, RE_DIGITAL_ASSETS_FOLDER)
    if digital_assets_dir is None:
        log.warning("  No *_digital_assets folder in %s — skipping", delivery_dir)
        return None

    log.info("    Digital assets: %s", digital_assets_dir.name)
    date_folders = scan_digital_assets(digital_assets_dir, base)

    summary["jobs_scanned"] += 1
    return {
        "projectFolder": job_dir.name,
        "wbrtFolder":    delivery_dir.name,
        "toFolder":      digital_assets_dir.name,
        "dateFolders":   date_folders,
    }


def scan_prefix(prefix_dir: Path) -> dict:
    """Scan a single prefix folder and return its full metadata dict."""
    name  = prefix_dir.name
    parts = name.split("_", 1)
    try:
        prefix_no = int(parts[0])
    except ValueError:
        prefix_no = None
    prefix_name = parts[1] if len(parts) > 1 else name

    log.info("=" * 60)
    log.info("Prefix: %s", name)
    summary["prefixes_scanned"] += 1

    projects: list[dict] = []
    for job_dir in _iter_dirs(prefix_dir, RE_JOB_FOLDER):
        log.info("  Job: %s", job_dir.name)
        job_meta = scan_job(job_dir, BASE_PATH)
        if job_meta:
            projects.append(job_meta)

    return {
        "prefixNo":   prefix_no,
        "prefixName": prefix_name,
        "projects":   projects,
    }


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def write_json(data: dict, prefix_name: str) -> None:
    """Write *data* as pretty-printed JSON to OUTPUT_PATH/<prefix_name>.json."""
    OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
    out_file = OUTPUT_PATH / f"{prefix_name}.json"
    try:
        out_file.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        log.info("Written → %s", out_file)
    except OSError as exc:
        log.error("Failed to write %s: %s", out_file, exc)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    if not BASE_PATH.exists():
        log.error("BASE_PATH does not exist: %s", BASE_PATH)
        log.error("Mount the network share first, then re-run.")
        sys.exit(1)

    log.info("=" * 60)
    log.info("ID-Direct Metadata Collector")
    log.info("Base path : %s", BASE_PATH)
    log.info("Output dir: %s", OUTPUT_PATH.resolve())
    log.info("=" * 60)

    prefix_dirs = list(_iter_dirs(BASE_PATH, RE_PREFIX_FOLDER))
    if not prefix_dirs:
        log.warning("No prefix folders found under %s", BASE_PATH)
        return

    for prefix_dir in prefix_dirs:
        prefix_data = scan_prefix(prefix_dir)
        write_json(prefix_data, prefix_dir.name)

    log.info("")
    log.info("=" * 60)
    log.info("SCAN COMPLETE — Summary")
    log.info("  Prefixes scanned      : %d", summary["prefixes_scanned"])
    log.info("  Jobs scanned          : %d", summary["jobs_scanned"])
    log.info("  Upload folders scanned: %d", summary["upload_folders_scanned"])
    log.info("  Files collected       : %d", summary["files_collected"])
    log.info("=" * 60)


if __name__ == "__main__":
    main()

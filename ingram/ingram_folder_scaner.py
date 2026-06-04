"""
=============================================================================
Ingram Server Upload Folder Metadata Collector
=============================================================================

Purpose:
    Recursively scans a network shared drive (ingram) and collects
    structured metadata about uploaded files and folders. Designed to feed
    an auto-upload automation system.

Folder Structure Assumptions:
    {BASE_PATH}/{prefix_folder}/{project_folder}/{wbrt_folder}/{to_folder}/
        {sequence_date_folder}/{upload_target_folder}/[files & subfolders]

    Levels:
        prefix_folder       — e.g. 9089_feral_house      (\d+_.+)
        project_folder      — e.g. 147885                (\d+.+)
        wbrt_folder         — e.g. 147885_WBRT            (\d+_WBRT)
        to_folder           — e.g. 147885_to              (\d+_to)
        sequence_date_folder— e.g. 01_12.26.25            (\d+_.+)
        upload_target_folder— e.g. To_Client              (any name)

    Only files/folders INSIDE upload_target_folder are collected.

How to Run:
    1. Mount your network share, e.g.:
          smb://172.16.100.50/ingram  →  /Volumes/ingram
    2. Adjust BASE_PATH below if your mount point differs.
    3. Run:
          python3 scan_ingram.py
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

BASE_PATH: Path = Path("/Volumes/ingram")
OUTPUT_PATH: Path = Path("./output")

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

RE_PREFIX_FOLDER   = re.compile(r"^\d+_.+$")
RE_PROJECT_FOLDER  = re.compile(r"^\d+.+$")
RE_WBRT_FOLDER     = re.compile(r"^\d+_WBRT$", re.IGNORECASE)
RE_TO_FOLDER       = re.compile(r"^\d+_to$",   re.IGNORECASE)
RE_SEQUENCE_FOLDER = re.compile(r"^\d+_.+$")

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
    "projects_scanned":       0,
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
# Tree builder
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


def scan_upload_targets(sequence_dir: Path, base: Path) -> list[dict]:
    """
    Iterate all upload-target folders inside a sequence/date folder.
    No name filtering — accept any folder name.
    Returns a list of uploadTarget dicts.
    """
    targets: list[dict] = []

    for target_dir in _iter_dirs(sequence_dir):      # no pattern — accept all
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


def scan_to_folder(to_dir: Path, base: Path) -> list[dict]:
    """
    Iterate all sequence/date folders inside a *_to folder.
    Returns a list of sequenceFolder dicts.
    """
    date_folders: list[dict] = []

    for seq_dir in _iter_dirs(to_dir, RE_SEQUENCE_FOLDER):
        log.info("      Sequence folder: %s", seq_dir.name)
        upload_targets = scan_upload_targets(seq_dir, base)
        if upload_targets:
            date_folders.append({
                "sequenceFolder": seq_dir.name,
                "uploadTargets":  upload_targets,
            })

    return date_folders


def scan_project(project_dir: Path, base: Path) -> Optional[dict]:
    """
    Scan a single project folder: locate *_WBRT → *_to → date folders.
    Returns a project dict or None if structure is not found.
    """
    wbrt_dir = _find_first_dir(project_dir, RE_WBRT_FOLDER)
    if wbrt_dir is None:
        log.warning("  No *_WBRT folder found in %s — skipping", project_dir)
        return None

    to_dir = _find_first_dir(wbrt_dir, RE_TO_FOLDER)
    if to_dir is None:
        log.warning("  No *_to folder found in %s — skipping", wbrt_dir)
        return None

    log.info("    to folder: %s", to_dir.name)
    date_folders = scan_to_folder(to_dir, base)

    summary["projects_scanned"] += 1
    return {
        "projectFolder": project_dir.name,
        "wbrtFolder":    wbrt_dir.name,
        "toFolder":      to_dir.name,
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
    for project_dir in _iter_dirs(prefix_dir, RE_PROJECT_FOLDER):
        log.info("  Project: %s", project_dir.name)
        project_meta = scan_project(project_dir, BASE_PATH)
        if project_meta:
            projects.append(project_meta)

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
    log.info("Ingram Metadata Collector")
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
    log.info("  Projects scanned      : %d", summary["projects_scanned"])
    log.info("  Upload folders scanned: %d", summary["upload_folders_scanned"])
    log.info("  Files collected       : %d", summary["files_collected"])
    log.info("=" * 60)


if __name__ == "__main__":
    main()
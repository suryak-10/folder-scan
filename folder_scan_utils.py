import os


def crawl_tree(path: str, indent: str = "      ") -> dict:
    """Recursively list all files and folders inside a directory."""
    node = {
        "name": os.path.basename(path) or path,
        "type": "folder",
        "path": path,
        "children": [],
    }

    try:
        entries = sorted(os.scandir(path), key=lambda e: (not e.is_dir(), e.name.lower()))
    except PermissionError:
        print(f"{indent}⚠️  Permission denied: {path}")
        return node
    except Exception as ex:
        print(f"{indent}⚠️  Error reading {path}: {ex}")
        return node

    for entry in entries:
        if entry.is_dir():
            print(f"{indent}📁  {entry.name}")
            node["children"].append(crawl_tree(entry.path, indent=indent + "  "))
            continue

        print(f"{indent}📄  {entry.name}")
        file_node = {
            "name": entry.name,
            "type": "file",
            "path": entry.path,
        }
        try:
            file_node["size_bytes"] = entry.stat().st_size
        except Exception:
            file_node["size_bytes"] = None
        node["children"].append(file_node)

    return node


def count_nodes(node: dict) -> tuple[int, int]:
    """Return folder and file counts for a tree node."""
    folders = 1 if node.get("type") == "folder" else 0
    files = 1 if node.get("type") == "file" else 0

    for child in node.get("children", []):
        child_folders, child_files = count_nodes(child)
        folders += child_folders
        files += child_files

    return folders, files

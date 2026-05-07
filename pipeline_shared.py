import copy
import json
import os
import shutil
import subprocess
import sys


REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
PIPELINE_CONFIG_PATH = os.path.join(REPO_ROOT, "_json", "pipeline_config.json")
LEGACY_RRRENDER_PATHS_PATH = os.path.join(REPO_ROOT, "_json", "rrRender_project_paths.json")
SETUP_APP_LAUNCH_LOG_PATH = os.path.join(REPO_ROOT, "_json", "project_setup_app_launch.log")

DEFAULT_PROJECT_ALIASES = {
    "THE_TRAP": "THE_TRAP",
    "TTM": "THE_TRAP",
    "TRAP": "THE_TRAP",
    "ARBOBION": "ARBOBION",
    "ARBO_BION": "ARBOBION",
    "ARB": "ARBOBION",
    "BTS": "BTS",
    "CKR": "CKR",
    "DSC": "DSC",
    "FUZZ": "FUZZ",
    "COC": "COC",
}


def _normalize_slashes(value):
    return str(value or "").replace("\\", "/")


def expand_path(path_value):
    expanded = os.path.expandvars(os.path.expanduser(str(path_value or "")))
    return _normalize_slashes(expanded)


def load_pipeline_config(config_path=PIPELINE_CONFIG_PATH):
    if not os.path.exists(config_path):
        return {
            "version": 1,
            "project_aliases": dict(DEFAULT_PROJECT_ALIASES),
            "projects": {},
            "profiles": {},
            "tool_paths": {},
        }

    with open(config_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict):
        raise ValueError("pipeline_config.json must contain a JSON object.")

    payload.setdefault("project_aliases", dict(DEFAULT_PROJECT_ALIASES))
    payload.setdefault("projects", {})
    payload.setdefault("profiles", {})
    payload.setdefault("tool_paths", {})
    return payload


def save_pipeline_config(payload, config_path=PIPELINE_CONFIG_PATH):
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def get_alias_map(payload=None):
    payload = payload or load_pipeline_config()
    alias_map = dict(DEFAULT_PROJECT_ALIASES)
    alias_map.update(payload.get("project_aliases", {}) or {})
    return dict((str(key).upper(), str(value).upper()) for key, value in alias_map.items())


def normalize_project_name(project_name, payload=None):
    raw_name = str(project_name or "").strip()
    if not raw_name:
        return ""
    alias_map = get_alias_map(payload)
    return alias_map.get(raw_name.upper(), raw_name.upper())


def get_project_names(payload=None):
    payload = payload or load_pipeline_config()
    return sorted(payload.get("projects", {}).keys())


def get_project_entry(project_name, payload=None):
    payload = payload or load_pipeline_config()
    normalized_name = normalize_project_name(project_name, payload)
    project = (payload.get("projects", {}) or {}).get(normalized_name)
    if not isinstance(project, dict):
        return None
    return copy.deepcopy(project)


def get_project_paths(project_name, payload=None):
    project = get_project_entry(project_name, payload)
    if not project:
        return {}
    return copy.deepcopy(project.get("paths", {}) or {})


def get_project_prefix(project_name, payload=None):
    project = get_project_entry(project_name, payload)
    if not project:
        return ""
    identity = project.get("identity", {}) or {}
    return str(identity.get("project_prefix", "") or "")


def get_tool_paths(tool_name, payload=None):
    payload = payload or load_pipeline_config()
    tool_paths = payload.get("tool_paths", {}) or {}
    entry = tool_paths.get(tool_name, {}) or {}
    return copy.deepcopy(entry)


def get_scene_depth_map(project_name, payload=None):
    payload = payload or load_pipeline_config()
    project = get_project_entry(project_name, payload) or {}
    scene_structure = project.get("scene_structure", {}) or {}
    depth_map = scene_structure.get("depth_map", {}) or {}
    scene_depth_value = scene_structure.get("scene_depth")
    if scene_depth_value not in (None, ""):
        scene_depth = int(scene_depth_value)
        return {
            "scene_depth": scene_depth,
            "cut_depth": int(scene_structure.get("cut_depth", scene_depth + 1) or scene_depth + 1),
            "process_depth": int(scene_structure.get("process_depth", scene_depth + 2) or scene_depth + 2),
            "file_depth": int(scene_structure.get("file_depth", scene_depth + 3) or scene_depth + 3),
        }
    return {
        "scene_depth": int(depth_map.get("scene_depth", 1) or 1),
        "cut_depth": int(depth_map.get("cut_depth", 2) or 2),
        "process_depth": int(depth_map.get("process_depth", 3) or 3),
        "file_depth": int(depth_map.get("file_depth", 4) or 4),
    }


def get_project_root_map(root_key="project_root", payload=None):
    payload = payload or load_pipeline_config()
    result = {}
    for project_name in get_project_names(payload):
        paths = get_project_paths(project_name, payload)
        root_path = expand_path(paths.get(root_key, ""))
        if root_path:
            result[project_name] = root_path
    return result


def _derive_scene_base_and_root_dir(project_root, scene_root):
    scene_root = _normalize_slashes(scene_root).rstrip("/")
    project_root = _normalize_slashes(project_root).rstrip("/")
    if project_root and scene_root.lower().startswith(project_root.lower() + "/"):
        relative = scene_root[len(project_root):].strip("/")
        return project_root + "/", relative or "scenes"
    return project_root + "/" if project_root else "", "scenes"


def _derive_asset_dirs(asset_root, categories):
    asset_root = _normalize_slashes(asset_root).rstrip("/")
    defaults = {"asset_ch_dir": "ch", "asset_bg_dir": "bg", "asset_prop_dir": "prop"}
    category_map = {}
    for category in categories or []:
        category_id = str((category or {}).get("id", "")).strip()
        root_path = _normalize_slashes((category or {}).get("root_path", "")).rstrip("/")
        if not category_id or not root_path:
            continue
        if asset_root and root_path.lower().startswith(asset_root.lower() + "/"):
            category_map[category_id] = root_path[len(asset_root):].strip("/")
        else:
            category_map[category_id] = category_id
    result = dict(defaults)
    if category_map.get("ch"):
        result["asset_ch_dir"] = category_map["ch"]
    if category_map.get("bg"):
        result["asset_bg_dir"] = category_map["bg"]
    if category_map.get("prop"):
        result["asset_prop_dir"] = category_map["prop"]
    return result


def build_legacy_rrrender_project_entry(project_name, payload=None):
    payload = payload or load_pipeline_config()
    project = get_project_entry(project_name, payload)
    if not project:
        return {}

    identity = project.get("identity", {}) or {}
    paths = project.get("paths", {}) or {}
    categories = (project.get("assets", {}) or {}).get("categories", []) or []
    scene_structure = project.get("scene_structure", {}) or {}
    scene_browser = project.get("scene_browser", {}) or {}
    browser_levels = scene_browser.get("levels", []) or []
    work_level = None
    for level in browser_levels:
        if str(level.get("id", "")).strip() == "work":
            work_level = level
            break

    project_root = expand_path(paths.get("project_root", ""))
    asset_root = expand_path(paths.get("asset_root", ""))
    scene_root = expand_path(paths.get("scene_root", ""))
    output_root = expand_path(paths.get("output_root", ""))
    cache_root = expand_path(paths.get("cache_root", ""))
    json_root = expand_path(paths.get("json_root", project_root))
    scene_base, scene_root_dir = _derive_scene_base_and_root_dir(project_root, scene_root)
    asset_dirs = _derive_asset_dirs(asset_root, categories)

    work_dir = str(scene_structure.get("work_folder_name", "") or "").strip()
    if not work_dir:
        work_dir = str((work_level or {}).get("default", "") or "")
    if not work_dir:
        fixed_options = (work_level or {}).get("fixed_options", []) or []
        work_dir = str(fixed_options[0]) if fixed_options else "ren"

    geometry_root_hint = ""
    for category in categories:
        hint = str((category or {}).get("geometry_root_hint", "") or "").strip()
        if hint:
            geometry_root_hint = hint
            break

    identifier_source = str(scene_structure.get("identifier_source", "") or "").strip().lower()
    scene_identifier_mode = "filename" if identifier_source == "filename" else "folder"

    result = {
        "drive": (project_root.rstrip("/") + "/") if project_root else "",
        "prefix": str(identity.get("project_prefix", project_name) or project_name),
        "asset_base": asset_root,
        "scene_base": scene_base,
        "project_json_base": json_root,
        "output_base": output_root,
        "scene_root_dir": scene_root_dir or "scenes",
        "ren_dir": work_dir or "ren",
        "cache_dir": str(scene_structure.get("cache_relative_path", "cache") or "cache"),
        "publish_dir": "pub",
        "scene_identifier_mode": scene_identifier_mode,
    }
    result.update(asset_dirs)
    if geometry_root_hint:
        result["geometry_root_hint"] = geometry_root_hint
    cache = project.get("cache", {}) or {}
    cache_root_template = str(cache.get("root_template", "") or "").strip()
    if cache_root_template:
        result["cache_base"] = cache_root_template
    elif cache_root:
        result["cache_base"] = cache_root
    return result


def sync_legacy_rrrender_paths_json(payload=None, output_path=LEGACY_RRRENDER_PATHS_PATH):
    payload = payload or load_pipeline_config()
    projects = {}
    for project_name in get_project_names(payload):
        projects[project_name] = build_legacy_rrrender_project_entry(project_name, payload)
    legacy_payload = {
        "version": 1,
        "projects": projects,
    }
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(legacy_payload, handle, ensure_ascii=False, indent=2)
    return output_path


def get_setup_app_path():
    return os.path.join(REPO_ROOT, "project_setup_app.py")


def _append_launch_log(message):
    try:
        os.makedirs(os.path.dirname(SETUP_APP_LAUNCH_LOG_PATH), exist_ok=True)
        with open(SETUP_APP_LAUNCH_LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(str(message).rstrip() + "\n")
    except Exception:
        pass


def _candidate_supports_tkinter(candidate_path):
    if not candidate_path or not os.path.exists(candidate_path):
        return False
    try:
        result = subprocess.run(
            [candidate_path, "-c", "import tkinter"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )
        return result.returncode == 0
    except Exception:
        return False


def get_best_python_launcher():
    executable = os.path.abspath(sys.executable)
    executable_dir = os.path.dirname(executable)
    candidates = [
        shutil.which("pythonw"),
        shutil.which("python"),
        os.path.join(executable_dir, "pythonw.exe"),
        os.path.join(executable_dir, "python.exe"),
        executable,
    ]
    for candidate in candidates:
        if _candidate_supports_tkinter(candidate):
            return candidate
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return executable


def launch_project_setup_app(tool_name=None, project_name=None, wait=True):
    app_path = get_setup_app_path()
    if not os.path.exists(app_path):
        raise FileNotFoundError(f"Project setup app not found: {app_path}")

    launcher = get_best_python_launcher()
    command = [launcher, app_path]
    if tool_name:
        command.extend(["--tool", str(tool_name)])
    if project_name:
        command.extend(["--project", str(project_name)])

    kwargs = {"cwd": REPO_ROOT}
    if os.name == "nt" and not wait:
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)

    _append_launch_log(f"launch wait={wait} launcher={launcher} command={command}")
    if wait:
        return_code = subprocess.call(command, **kwargs)
        _append_launch_log(f"exit code={return_code} command={command}")
        if return_code != 0:
            raise RuntimeError(f"Project setup app exited with code {return_code}")
        return return_code
    process = subprocess.Popen(command, **kwargs)
    _append_launch_log(f"spawn pid={process.pid} command={command}")
    return process

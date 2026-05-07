
bl_info = {
    "name": "SF Blender LookDev v2",
    "blender": (3, 0, 0),
    "category": "SF_Tools",
    "author": "Sean Hwang",
    "version": (1, 0),
    "location": "View3D > UI > LookDev",
    "description": "This addon provides a simple way to reference and delete LookDev lights in Blender.",
    "warning": "",
    "doc_url": "",
    "tracker_url": "",
}

import bpy
import os
from datetime import datetime
import bmesh
import math
from math import radians
import json
import re
import sys
import shutil
from bpy.utils import previews
from bpy.app.handlers import persistent

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_MODULE_SEARCH_PATHS = [
    THIS_DIR,
    r"C:\Users\hwang\Desktop\codex\sf_blendLdv_v2",
]
for search_path in SHARED_MODULE_SEARCH_PATHS:
    if search_path and os.path.isdir(search_path) and search_path not in sys.path:
        sys.path.append(search_path)

try:
    from pipeline_shared import (
        get_project_entry as get_pipeline_project_entry,
        get_project_prefix as get_pipeline_project_prefix,
        get_project_root_map,
        load_pipeline_config,
        save_pipeline_config,
        sync_legacy_rrrender_paths_json,
    )
    PIPELINE_SHARED_AVAILABLE = True
except Exception:
    get_pipeline_project_entry = None
    get_pipeline_project_prefix = None
    get_project_root_map = None
    load_pipeline_config = None
    save_pipeline_config = None
    sync_legacy_rrrender_paths_json = None
    PIPELINE_SHARED_AVAILABLE = False


@persistent
def make_paths_absolute(_dummy):
    bpy.ops.file.make_paths_absolute()

# --------------------
# Browser Config
# --------------------

PREFERRED_DRIVES = ["M:/", "S:/"]

STATE_FILE = os.path.join(os.environ["USERPROFILE"], "Documents", "_json", "ldv_browser_state.json")
print(f"[LDV DEBUG] STATE_FILE → {STATE_FILE}")
os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)

DEFAULT_PROJECTS = {
    "BTS": ("bts", "B:/assets"),
    "Trap": ("TheTrapMOVIE", "T:/assets"),
    "DSC": ("Dead Sorcerer's City", "S:/assets"),
    "FUZZ": ("FUZZ", "Z:/assets"),
    "COC": ("COC", "S:/PROJECT/COC/02_Production/CHSetup/controller"),
}
PROJECTS = dict(DEFAULT_PROJECTS)

CATEGORY_ITEMS = [
    ("ch", "CH", "Character"),
    ("bg", "BG", "Background"),
    ("prop", "PROP", "Props"),
]

COC_PROJECT = "COC"
COC_CATEGORY = "ch"

SCRIPT_PATH = r"M:\RND\SFtools\2025\lookdev\sf_blendLdv_v2.py"
SCRIPT_BACKUP_DIR = r"M:\RND\SFtools\2025\lookdev\_t"
DEPLOY_ALLOWED_USERS = {"hwang"}
HWANG_LOCAL_SCRIPT_PATH = r"C:\Users\hwang\Desktop\codex\sf_blendLdv_v2\sf_blendLdv_v2.py"
MODULE_NAME = "sf_blendLdv_v2"


def refresh_projects_from_pipeline():
    global PROJECTS
    if not PIPELINE_SHARED_AVAILABLE:
        PROJECTS = dict(DEFAULT_PROJECTS)
        return PROJECTS

    try:
        loaded_roots = get_project_root_map("asset_root") or {}
        if loaded_roots:
            updated = {}
            for project_name, asset_root in loaded_roots.items():
                prefix = get_pipeline_project_prefix(project_name) if get_pipeline_project_prefix else project_name
                updated[project_name] = (prefix or project_name, asset_root)
            PROJECTS = updated
        else:
            PROJECTS = dict(DEFAULT_PROJECTS)
    except Exception as exc:
        print(f"[LDV SETUP] Failed to load shared project config: {exc}")
        PROJECTS = dict(DEFAULT_PROJECTS)
    return PROJECTS


def clamp_project_index(tool):
    project_count = max(len(PROJECTS), 1)
    tool.project_index = max(0, min(tool.project_index, project_count - 1))


refresh_projects_from_pipeline()

def normalize_path(path):
    return os.path.normcase(os.path.abspath(path))


def can_show_deploy_tools():
    return os.environ.get("USERNAME", "").strip().lower() in {user.lower() for user in DEPLOY_ALLOWED_USERS}


def get_update_source_path():
    if os.environ.get("USERNAME", "").strip().lower() == "hwang":
        return HWANG_LOCAL_SCRIPT_PATH
    return SCRIPT_PATH


def get_next_script_backup_path(target_path=SCRIPT_PATH, backup_dir=SCRIPT_BACKUP_DIR):
    base_name = os.path.splitext(os.path.basename(target_path))[0]
    extension = os.path.splitext(target_path)[1]
    version_pattern = re.compile(
        rf"^{re.escape(base_name)}_v(\d+)(?:.*){re.escape(extension)}$",
        re.IGNORECASE,
    )

    max_version = 0
    if os.path.isdir(backup_dir):
        for file_name in os.listdir(backup_dir):
            match = version_pattern.match(file_name)
            if not match:
                continue
            max_version = max(max_version, int(match.group(1)))

    next_version = max_version + 1
    backup_name = f"{base_name}_v{next_version:03d}{extension}"
    return os.path.join(backup_dir, backup_name), next_version

class DEV_OT_reload_blendldv(bpy.types.Operator):
    """외부 blendldv.py 다시 불러오기"""
    bl_idname = "dev.reload_blendldv"
    bl_label = "Reload blendldv"
    bl_options = {'REGISTER', 'INTERNAL'}

    def execute(self, context):
        module_name = MODULE_NAME
        source_path = get_update_source_path()
        server_path = source_path

        if module_name in sys.modules:
            mod = sys.modules[module_name]
            local_path = os.path.abspath(mod.__file__)
        else:
            self.report({'ERROR'}, f"{module_name} 모듈을 찾을 수 없음")
            return {'CANCELLED'}

        # 서버 → 로컬 복사
        try:
            shutil.copy2(source_path, local_path)
            self.report({'INFO'}, f"{server_path} → {local_path} 복사 완료")
        except Exception as e:
            self.report({'ERROR'}, f"복사 실패: {e}")
            return {'CANCELLED'}

        # 🔄 Blender 전체 스크립트 리로드
        bpy.ops.script.reload()

        return {'FINISHED'}


class DEV_OT_deploy_blendldv(bpy.types.Operator):
    """濡쒖뺄 ?묎컻蹂몄쓣 rrRender ?덉뿉 蹂듭궗"""
    bl_idname = "dev.deploy_blendldv"
    bl_label = "Deploy blendldv"
    bl_options = {'REGISTER', 'INTERNAL'}

    def execute(self, context):
        source_path = get_blendldv_source_path()
        if not source_path or not os.path.exists(source_path):
            self.report({'ERROR'}, "濡쒖뺄 ?묎컻蹂??뚯씪??李얠쓣 ???놁쓬")
            return {'CANCELLED'}

        try:
            shutil.copy2(source_path, LOCAL_DEPLOY_SCRIPT_PATH)
        except Exception as e:
            self.report({'ERROR'}, f"Deploy ?ㅽ뙣: {e}")
            return {'CANCELLED'}

        self.report({'INFO'}, f"{LOCAL_DEPLOY_SCRIPT_PATH} ?앹꽦 ?꾨즺")
        return {'FINISHED'}


def _reload_blendldv_execute(self, context):
    module_name = MODULE_NAME
    source_path = get_update_source_path()

    if module_name in sys.modules:
        mod = sys.modules[module_name]
        local_path = os.path.abspath(mod.__file__)
    else:
        self.report({'ERROR'}, f"{module_name} module not found")
        return {'CANCELLED'}

    try:
        shutil.copy2(source_path, local_path)
    except Exception as e:
        self.report({'ERROR'}, f"Reload failed: {e}")
        return {'CANCELLED'}

    self.report({'INFO'}, f"{source_path} -> {local_path} copy complete")
    bpy.ops.script.reload()
    return {'FINISHED'}


def _deploy_blendldv_invoke(self, context, event):
    return context.window_manager.invoke_confirm(self, event)


def _deploy_blendldv_execute(self, context):
    local_path = os.path.abspath(__file__)
    target_path = SCRIPT_PATH
    backup_dir = SCRIPT_BACKUP_DIR

    if not can_show_deploy_tools():
        self.report({'WARNING'}, "Deploy is allowed only for approved users.")
        return {'CANCELLED'}

    if not os.path.exists(local_path):
        self.report({'ERROR'}, f"Local script not found: {local_path}")
        return {'CANCELLED'}

    if normalize_path(local_path) == normalize_path(target_path):
        self.report({'WARNING'}, "This script is already running from the deploy path.")
        return {'CANCELLED'}

    try:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        os.makedirs(backup_dir, exist_ok=True)

        backup_path = None
        if os.path.exists(target_path):
            backup_path, version_number = get_next_script_backup_path(target_path, backup_dir)
            shutil.copy2(target_path, backup_path)
            print(f"[DEPLOY] Existing deploy backup complete: v{version_number:03d} -> {backup_path}")

        shutil.copy2(local_path, target_path)
        message = f"Deploy complete: {local_path} -> {target_path}"
        if backup_path:
            message += f" | backup: {os.path.basename(backup_path)}"
        self.report({'INFO'}, message)
        print(f"[DEPLOY] {message}")
        return {'FINISHED'}
    except Exception as e:
        self.report({'ERROR'}, f"Deploy failed: {e}")
        return {'CANCELLED'}


DEV_OT_reload_blendldv.execute = _reload_blendldv_execute
DEV_OT_deploy_blendldv.invoke = _deploy_blendldv_invoke
DEV_OT_deploy_blendldv.execute = _deploy_blendldv_execute


if not os.path.exists(STATE_FILE):
    print("[LDV DEBUG] STATE_FILE does not exist, creating...")
    with open(STATE_FILE, 'w') as f:
        json.dump({}, f, indent=2)
else:
    print("[LDV DEBUG] STATE_FILE already exists.")


def get_active_drive():
    for drive in PREFERRED_DRIVES:
        if os.path.exists(drive):
            return drive
    return PREFERRED_DRIVES[0]

def resolve_drive_path(relative_path):
    for drive in PREFERRED_DRIVES:
        full_path = os.path.join(drive, relative_path)
        if os.path.exists(full_path):
            return full_path
    return os.path.join(PREFERRED_DRIVES[0], relative_path)

def resolve_project_path(path_type, subpath=""):
    drive = get_active_drive()
    if drive.upper().startswith("S:"):
        base = os.path.join(drive, "assets", "scripts", path_type)
    else:
        if path_type == "presets":
            base = os.path.join(drive, "RND", "SFtools", "2025", "lookdev", "presets")
        else:
            base = os.path.join(drive, "RND", "SFtools", "2025", "lookdev", path_type)
    return os.path.join(base, subpath) if subpath else base

def resolve_script_path(subfolder, filename):
    return resolve_project_path(subfolder, filename)

def resolve_preset_path(filename):
    return resolve_project_path("presets", filename)

def resolve_cache_path(subpath=""):
    return resolve_project_path("cache", subpath)

def save_browser_state(tool):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)  # ← 여기에서만!
    with open(STATE_FILE, "w") as f:
        json.dump({
            "project_index": tool.project_index,
            "category": tool.category,
            "asset_enum": tool.asset_enum,
            "version_enum": getattr(tool, "version_enum", ""),
            "project": getattr(tool, "project", ""),
            "filepath": bpy.data.filepath or "",
        }, f)

CACHE_ROOT = resolve_cache_path()  # ✅ 드라이브 환경에 따라 자동 전환


def read_browser_state_file():
    try:
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def write_browser_state_file(state_dict):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        json.dump(state_dict, f, indent=2)

def init_browser_state_file():
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    if not os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'w') as f:
            json.dump({}, f, indent=2)


def is_coc_project(project):
    return project == COC_PROJECT


def get_project_base_path(project):
    return PROJECTS[project][1]


def get_project_asset_root(project, category):
    base_path = get_project_base_path(project)
    if is_coc_project(project):
        return base_path
    return os.path.join(base_path, category)


def get_project_asset_dir(project, category, asset):
    base_path = get_project_base_path(project)
    if is_coc_project(project):
        return os.path.join(base_path, asset)
    return os.path.join(base_path, category, asset)


def get_project_blend_dir(project, category, asset):
    return os.path.join(get_project_asset_dir(project, category, asset), "mod", "blend")


def get_project_publish_blend_path(project, category, asset):
    return os.path.join(get_project_asset_dir(project, category, asset), "mod", f"{asset}.blend")


def get_category_enum_items(self, context):
    project = self.project if hasattr(self, "project") else None
    if project == COC_PROJECT:
        return [item for item in CATEGORY_ITEMS if item[0] == COC_CATEGORY]
    return CATEGORY_ITEMS


def get_scene_asset_mod_dir(category, asset_name):
    base_path = get_project_path()
    if get_project_prefix() == "coc":
        return os.path.join(base_path, asset_name, "mod")
    return os.path.join(base_path, "assets", category, asset_name, "mod")


def get_coc_render_output_dir(asset_name):
    render_root = os.path.join(get_project_path(), asset_name, "sheet", "render")
    os.makedirs(render_root, exist_ok=True)

    max_version = 0
    version_pattern = re.compile(r"^v(\d{3})$", re.IGNORECASE)
    for entry in os.listdir(render_root):
        entry_path = os.path.join(render_root, entry)
        if not os.path.isdir(entry_path):
            continue
        match = version_pattern.match(entry)
        if not match:
            continue
        max_version = max(max_version, int(match.group(1)))

    next_dir = os.path.join(render_root, f"v{max_version + 1:03d}")
    os.makedirs(next_dir, exist_ok=True)
    return next_dir



# ===================================
# LookDev Browser Core Functions
# ===================================
thumb_previews = None
_cached_items = {}

def get_asset_enum_items(self, context):
    items = []
    if hasattr(self, "category"):
        cat = self.category
        if cat == "ch":
            items = [('hero', 'Hero', ''), ('npc', 'NPC', '')]
        elif cat == "bg":
            items = [('street', 'Street', ''), ('building', 'Building', '')]
    return items

# update 핸들러 함수
def on_category_update(self, ctx):
    self.update_category(ctx)
    save_browser_state(self)
    # return None

def on_asset_enum_update(self, ctx):
    save_browser_state(self)
    return None



            

# ---------------------------
# Thumbnail Cache
# ---------------------------
def get_cache_path(proj_key):
    return os.path.join(CACHE_ROOT, proj_key, "assetList.json")

def load_cache(proj_key):
    path = get_cache_path(proj_key)
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {}

def get_asset_enum_items(self, context):
    global _cached_items, thumb_previews
    project = self.project
    category = self.category
    key = f"{project}_{category}"

    if key in _cached_items:
        return _cached_items[key]

    project_cache = load_cache(project)
    if category not in project_cache:
        update_asset_list_cache(project)
        project_cache = load_cache(project)

    cache = project_cache.get(category, {})
    items = []
    lowercase_cache = {k.lower(): k for k in cache.keys()}

    for i, asset_lower in enumerate(sorted(lowercase_cache.keys())):
        asset = lowercase_cache[asset_lower]
        thumb_path = os.path.join(CACHE_ROOT, project, "thumbnails", category, f"{asset}.png")
        if asset not in thumb_previews:
            try:
                thumb_previews.load(asset, thumb_path, 'IMAGE')
            except:
                continue
        icon_id = thumb_previews[asset].icon_id
        items.append((asset, asset, "", icon_id, i))

    if not items:
        items.append(('NONE', 'No Images Found', '', 'ERROR', 0))

    _cached_items[key] = items
    return items

# ---------------------------
# Version Enum Items
# ---------------------------
def get_version_enum_items(self, context):
    project = self.project
    category = self.category
    asset = self.asset_enum
    items = []
    if asset and asset != "NONE":
        asset_blend_dir = get_project_blend_dir(project, category, asset)
        if os.path.exists(asset_blend_dir):
            blends = [os.path.join(asset_blend_dir, f) for f in os.listdir(asset_blend_dir)
                      if f.endswith(".blend") and f.startswith(asset)]
            blends.sort(key=lambda x: os.path.getmtime(x), reverse=True)
            for i, filepath in enumerate(blends):
                blend_file = os.path.basename(filepath)
                items.append((blend_file, blend_file, "", 'FILE_BLEND', i))
    if not items:
        items.append(('NONE', 'No Versions Found', '', 'ERROR', 0))
    items.insert(0, ("LATEST", "Latest Publish", "", 'FILE_TICK', -1))
    return items

# ---------------------------
# Property Group
# ---------------------------
# 완전 교체된 PropertyGroup
# class LdvBrowserProperties(bpy.types.PropertyGroup):
    # project_index: bpy.props.IntProperty(default=0)
    # category: bpy.props.StringProperty(default="ch")


class LdvBrowserProperties(bpy.types.PropertyGroup):
    project_index: bpy.props.IntProperty(default=0)
    category: bpy.props.EnumProperty(
        name="Category",
        items=get_category_enum_items,
        update=on_category_update
    )

    asset_enum: bpy.props.EnumProperty(
        name="Gallery",
        items=get_asset_enum_items,
        update=lambda self, ctx: save_browser_state(self)
    )
    version_enum: bpy.props.EnumProperty(
        name="Version",
        items=get_version_enum_items
    )

    @property
    def project(self):
        keys = list(PROJECTS.keys())
        if not keys:
            return COC_PROJECT
        safe_index = max(0, min(self.project_index, len(keys) - 1))
        return keys[safe_index]

    def update_category(self, context):
        if self.project == COC_PROJECT and self.category != COC_CATEGORY:
            self.category = COC_CATEGORY
        key = f"{self.project}_{self.category}"
        if key in _cached_items:
            del _cached_items[key]

# ====================================================
# 씬 열 때 자동 복원
# ====================================================
def load_scene_post_handler(dummy):
    tool = bpy.context.scene.ldv_browser_tool
    if not sync_browser_state_to_current_file(tool, bpy.data.filepath, save_state=True):
        load_browser_state(tool)

# ====================================================
# 초고속 스냅샷 + 완전 복원
# ====================================================
def render_thumbnail_from_viewport(obj, filepath):
    size = 128
    scene = bpy.context.scene
    view_layer = bpy.context.view_layer
    area = next((a for a in bpy.context.screen.areas if a.type == 'VIEW_3D'), None)
    if not area:
        raise RuntimeError("No active 3D View found")

    original_settings = {
        "engine": scene.render.engine,
        "samples": scene.eevee.taa_render_samples 
            if scene.render.engine in ['BLENDER_EEVEE', 'BLENDER_EEVEE_NEXT'] else 0,
        "resolution_x": scene.render.resolution_x,
        "resolution_y": scene.render.resolution_y,
        "filepath": scene.render.filepath,
        "use_compositing": scene.render.use_compositing,
        "use_sequencer": scene.render.use_sequencer,
        "use_border": scene.render.use_border,
        "use_crop_to_border": scene.render.use_crop_to_border,
        "view_layer_use": view_layer.use
    }

    if scene.render.engine == 'CYCLES':
        original_settings.update({
            "cycles_samples": scene.cycles.samples,
            "cycles_max_bounces": scene.cycles.max_bounces,
        })

    scene.render.engine = get_eevee_engine_name()
    if scene.render.engine == 'BLENDER_EEVEE' or scene.render.engine == 'BLENDER_EEVEE_NEXT':
        scene.eevee.taa_render_samples = 4
        scene.render.resolution_x = size
        scene.render.resolution_y = size
        scene.render.filepath = filepath
        scene.render.image_settings.file_format = 'PNG'
        scene.render.use_compositing = False
        scene.render.use_sequencer = False
        scene.render.use_border = False
        scene.render.use_crop_to_border = False
        view_layer.use = True

    space = area.spaces.active
    cam_data = bpy.data.cameras.new("TempCamData")
    cam = bpy.data.objects.new("TempCam", cam_data)
    bpy.context.collection.objects.link(cam)
    cam.matrix_world = space.region_3d.view_matrix.inverted()
    old_cam = scene.camera
    scene.camera = cam

    bpy.ops.render.render(write_still=True)

    scene.render.engine = original_settings["engine"]
    scene.render.resolution_x = original_settings["resolution_x"]
    scene.render.resolution_y = original_settings["resolution_y"]
    scene.render.filepath = original_settings["filepath"]
    scene.render.use_compositing = original_settings["use_compositing"]
    scene.render.use_sequencer = original_settings["use_sequencer"]
    scene.render.use_border = original_settings["use_border"]
    scene.render.use_crop_to_border = original_settings["use_crop_to_border"]
    view_layer.use = original_settings["view_layer_use"]

    if original_settings["engine"] == 'BLENDER_EEVEE':
        scene.eevee.taa_render_samples = original_settings["samples"]
    elif original_settings["engine"] == 'CYCLES':
        scene.cycles.samples = original_settings.get("cycles_samples", 128)
        scene.cycles.max_bounces = original_settings.get("cycles_max_bounces", 12)

    scene.camera = old_cam
    bpy.data.objects.remove(cam, do_unlink=True)
    bpy.data.cameras.remove(cam_data, do_unlink=True)


# ====================================================
# 오퍼레이터
# ====================================================
class LDV_OT_ProjectPrev(bpy.types.Operator):
    bl_idname = "ldv.project_prev"
    bl_label = "Prev Project"
    def execute(self, context):
        refresh_projects_from_pipeline()
        tool = context.scene.ldv_browser_tool
        clamp_project_index(tool)
        tool.project_index = (tool.project_index - 1) % len(PROJECTS)
        if tool.project == COC_PROJECT:
            tool.category = COC_CATEGORY
        tool.update_category(context)
        save_browser_state(tool)
        return {'FINISHED'}

class LDV_OT_ProjectNext(bpy.types.Operator):
    bl_idname = "ldv.project_next"
    bl_label = "Next Project"
    def execute(self, context):
        refresh_projects_from_pipeline()
        tool = context.scene.ldv_browser_tool
        clamp_project_index(tool)
        tool.project_index = (tool.project_index + 1) % len(PROJECTS)
        if tool.project == COC_PROJECT:
            tool.category = COC_CATEGORY
        tool.update_category(context)
        save_browser_state(tool)
        return {'FINISHED'}

# class LDV_OT_RefreshGallery(bpy.types.Operator):
    # bl_idname = "ldv.refresh_gallery"
    # bl_label = "Update"
    # def execute(self, context):
        # global _cached_items, thumb_previews
        # tool = context.scene.ldv_browser_tool
        # key = f"{tool.project}_{tool.category}"

        # # ✅ assetList 갱신
        # update_asset_list_cache(tool.project)

        # # ✅ 썸네일 캐시 초기화
        # if key in _cached_items:
            # del _cached_items[key]
        # bpy.utils.previews.remove(thumb_previews)
        # thumb_previews = bpy.utils.previews.new()

        # # ✅ UI 갱신
        # tool.asset_enum = tool.asset_enum
        # self.report({'INFO'}, f"Gallery & cache updated for {tool.project}/{tool.category}")
        # return {'FINISHED'}

class LDV_OT_RefreshGallery(bpy.types.Operator):
    bl_idname = "ldv.refresh_gallery"
    bl_label = "Update"
    
    def execute(self, context):
        global _cached_items, thumb_previews
        tool = context.scene.ldv_browser_tool
        
        # 1. 캐시 키 및 리스트 갱신
        key = f"{tool.project}_{tool.category}"
        
        # assetList.json 파일 갱신 (실제 폴더 스캔)
        update_asset_list_cache(tool.project)

        # 2. 내부 캐시 변수 및 썸네일 초기화
        if key in _cached_items:
            del _cached_items[key]
        
        if thumb_previews:
            bpy.utils.previews.remove(thumb_previews)
        thumb_previews = bpy.utils.previews.new()

        # 3. [핵심] 갱신된 에셋 리스트 미리 가져오기
        # 이 시점에서 new_items는 [('cockroach', ...), ('light', ...)] 같은 리스트가 됨
        new_items = get_asset_enum_items(tool, context)
        new_ids = [item[0] for item in new_items]  # ID만 추출: ['cockroach', 'light', ...]

        # 4. [수정됨] 현재 값이 유효한지 검사 후 할당
        # 현재 값(tool.asset_enum)이 빈 문자열("")이거나 리스트에 없는 값이라면
        if tool.asset_enum not in new_ids:
            if new_ids:
                # 리스트가 비어있지 않다면 첫 번째 에셋(예: 'cockroach')을 강제로 선택
                print(f"[LDV FIX] Invalid asset '{tool.asset_enum}' found. Resetting to '{new_ids[0]}'")
                tool.asset_enum = new_ids[0]
            else:
                # 리스트가 아예 비었으면(NONE) 어쩔 수 없이 패스
                pass
        else:
            # 값이 유효하다면(목록에 있다면) 자기 자신을 다시 할당해 UI 갱신 트리거
            tool.asset_enum = tool.asset_enum

        self.report({'INFO'}, f"Gallery & cache updated for {tool.project}/{tool.category}")
        return {'FINISHED'}


class LDV_OT_OpenProjectSetupApp(bpy.types.Operator):
    bl_idname = "ldv.open_project_setup_app"
    bl_label = "Setup"

    project_name: bpy.props.StringProperty(name="Project")
    project_root: bpy.props.StringProperty(name="Project Root", subtype='DIR_PATH')
    asset_root: bpy.props.StringProperty(name="Asset Root", subtype='DIR_PATH')
    scene_root: bpy.props.StringProperty(name="Scene Root", subtype='DIR_PATH')
    output_root: bpy.props.StringProperty(name="Output Root", subtype='DIR_PATH')
    json_root: bpy.props.StringProperty(name="Json Root", subtype='DIR_PATH')
    project_prefix: bpy.props.StringProperty(name="Prefix")

    def invoke(self, context, event):
        tool = context.scene.ldv_browser_tool
        self.project_name = tool.project
        if PIPELINE_SHARED_AVAILABLE and load_pipeline_config and get_pipeline_project_entry:
            payload = load_pipeline_config()
            project = get_pipeline_project_entry(self.project_name, payload) or {}
            identity = project.get("identity", {}) or {}
            paths = project.get("paths", {}) or {}
            self.project_prefix = str(identity.get("project_prefix", "") or "")
            self.project_root = str(paths.get("project_root", "") or "")
            self.asset_root = str(paths.get("asset_root", "") or "")
            self.scene_root = str(paths.get("scene_root", "") or "")
            self.output_root = str(paths.get("output_root", "") or "")
            self.json_root = str(paths.get("json_root", "") or "")
        return context.window_manager.invoke_props_dialog(self, width=680)

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        box.label(text=f"Project: {self.project_name}", icon='TOOL_SETTINGS')
        col = box.column(align=True)
        col.prop(self, "project_prefix")
        col.prop(self, "project_root")
        col.prop(self, "asset_root")
        col.prop(self, "scene_root")
        col.prop(self, "output_root")
        col.prop(self, "json_root")

    def execute(self, context):
        if not PIPELINE_SHARED_AVAILABLE:
            self.report({'WARNING'}, "Shared project setup app is unavailable.")
            return {'CANCELLED'}

        tool = context.scene.ldv_browser_tool
        try:
            payload = load_pipeline_config()
            project = get_pipeline_project_entry(self.project_name, payload) or {"identity": {}, "paths": {}, "assets": {}}
            identity = project.setdefault("identity", {})
            paths = project.setdefault("paths", {})
            assets = project.setdefault("assets", {})

            identity["project_id"] = self.project_name
            identity["project_prefix"] = self.project_prefix.strip()
            paths["project_root"] = self.project_root.strip()
            paths["asset_root"] = self.asset_root.strip()
            paths["scene_root"] = self.scene_root.strip()
            paths["output_root"] = self.output_root.strip()
            paths["json_root"] = self.json_root.strip()

            categories = assets.get("categories", []) if isinstance(assets.get("categories"), list) else []
            if self.asset_root.strip() and categories:
                for item in categories:
                    if not isinstance(item, dict):
                        continue
                    category_id = str(item.get("id", "")).strip()
                    if category_id in {"ch", "bg", "prop"}:
                        item["root_path"] = os.path.join(self.asset_root.strip(), category_id).replace("\\", "/")
                assets["categories"] = categories

            payload.setdefault("projects", {})[self.project_name] = project
            save_pipeline_config(payload)
            sync_legacy_rrrender_paths_json(payload)
            refresh_projects_from_pipeline()
            clamp_project_index(tool)
            if tool.project == COC_PROJECT:
                tool.category = COC_CATEGORY
            tool.update_category(context)
            save_browser_state(tool)
            self.report({'INFO'}, f"Saved project setup for {self.project_name}")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, f"Failed to save Blender setup: {exc}")
            return {'CANCELLED'}

class LDV_OT_CaptureThumbnail(bpy.types.Operator):
    bl_idname = "ldv.capture_thumbnail"
    bl_label = "Capture"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        tool = context.scene.ldv_browser_tool
        project, category, asset = tool.project, tool.category, tool.asset_enum

        if not asset or asset == 'NONE':
            self.report({'ERROR'}, "No asset selected to capture thumbnail.")
            return {'CANCELLED'}

        thumb_path = os.path.join(
            CACHE_ROOT, project, "thumbnails", category, f"{asset}.png"
        )
        os.makedirs(os.path.dirname(thumb_path), exist_ok=True)

        obj = context.active_object
        if not obj:
            self.report({'ERROR'}, "No active object selected.")
            return {'CANCELLED'}

        try:
            render_thumbnail_from_viewport(obj, thumb_path)
            self.report({'INFO'}, f"Thumbnail saved: {thumb_path}")
            bpy.ops.ldv.refresh_gallery()
        except Exception as e:
            self.report({'ERROR'}, f"Snapshot failed: {e}")
            return {'CANCELLED'}

        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)


class LDV_OT_OpenBlendFile(bpy.types.Operator):
    bl_idname = "ldv.open_blend_file"
    bl_label = "Open"
    def execute(self, context):
        tool = context.scene.ldv_browser_tool
        project, category, asset, version = tool.project, tool.category, tool.asset_enum, tool.version_enum

        if not asset or asset == 'NONE' or not version or version == 'NONE':
            self.report({'ERROR'}, "Incomplete selection.")
            return {'CANCELLED'}

        if version == "LATEST":
            blend_file = get_project_publish_blend_path(project, category, asset)
        else:
            blend_file = os.path.join(get_project_blend_dir(project, category, asset), version)

        if not os.path.exists(blend_file):
            self.report({'ERROR'}, f"Blend file not found: {blend_file}")
            return {'CANCELLED'}

        save_browser_state(tool)
        bpy.ops.wm.open_mainfile(filepath=blend_file)
        return {'FINISHED'}

class LDV_OT_SaveAsV001(bpy.types.Operator):
    bl_idname = "ldv.save_as_v001"
    bl_label = "Save As v001"

    def execute(self, context):
        assets, category = get_assets()
        if not assets:
            self.report({'ERROR'}, "현재 열린 파일 경로에서 에셋 정보를 추출할 수 없습니다.")
            return {'CANCELLED'}

        asset = assets[0][0]
        base_path = get_project_path()
        if get_project_prefix() == "coc":
            version_path = os.path.join(base_path, asset, "mod", "blend")
        else:
            version_path = os.path.join(base_path, "assets", category, asset, "mod", "blend")
        os.makedirs(version_path, exist_ok=True)

        save_file_path = os.path.join(version_path, f"{asset}_v001.blend")
        bpy.ops.wm.save_as_mainfile(filepath=save_file_path)

        self.report({'INFO'}, f"Saved as {save_file_path}")
        return {'FINISHED'}


class LDV_OT_SaveIncremental(bpy.types.Operator):
    bl_idname = "ldv.save_incremental"
    bl_label = "Save Incremental (+1)"

    def execute(self, context):
        import re

        assets, category = get_assets()
        if not assets:
            self.report({'ERROR'}, "현재 열린 파일 경로에서 에셋 정보를 추출할 수 없습니다.")
            return {'CANCELLED'}

        asset = assets[0][0]
        base_path = get_project_path()
        if get_project_prefix() == "coc":
            version_path = os.path.join(base_path, asset, "mod", "blend")
        else:
            version_path = os.path.join(base_path, "assets", category, asset, "mod", "blend")
        os.makedirs(version_path, exist_ok=True)

        existing_versions = [f for f in os.listdir(version_path)
                             if f.endswith('.blend') and f.startswith(asset)]

        version_numbers = []
        for f in existing_versions:
            match = re.search(r'_v(\d{3})\.blend$', f)
            if match:
                version_numbers.append(int(match.group(1)))

        new_version = max(version_numbers) + 1 if version_numbers else 1

        new_filename = f"{asset}_v{new_version:03d}.blend"
        save_file_path = os.path.join(version_path, new_filename)
        bpy.ops.wm.save_as_mainfile(filepath=save_file_path)

        self.report({'INFO'}, f"Saved as {new_filename}")
        return {'FINISHED'}


class LDV_OT_ConfirmActionDialog(bpy.types.Operator):
    bl_idname = "ldv.confirm_action_dialog"
    bl_label = "Confirm Operation"

    __annotations__ = {
        "action": bpy.props.StringProperty(),
        "empty_mode": bpy.props.EnumProperty(
            name="Empty Mode",
            items=[
                ('COPY_CURRENT', "Use Current Scene", "Save current scene as is"),
                ('NEW_SCENE', "Start from Empty", "Empty scene and build new one")
            ],
            default='COPY_CURRENT'
        )
    }

    def execute(self, context):
        if self.action == 'open_empty':
            return self.handle_open_empty(context)
        elif self.action == 'open_file':
            return self.handle_open_asset(context)
        elif self.action == 'publish':
            return self.handle_publish(context)
        elif self.action == 'save_incremental':
            return self.handle_save_incremental(context)  # ✅ 이 줄 추가            
        return {'CANCELLED'}

    def handle_open_empty(self, context):
        import os
        import bpy

        tool = context.scene.ldv_browser_tool
        project, category, asset = tool.project, tool.category, tool.asset_enum

        if not asset or asset == 'NONE':
            self.report({'ERROR'}, "UI에서 어셋 이름을 선택해 주세요.")
            return {'CANCELLED'}

        version_path = get_project_blend_dir(project, category, asset)
        os.makedirs(version_path, exist_ok=True)
        save_path = os.path.join(version_path, f"{asset}_v000.blend")

        if self.empty_mode == 'NEW_SCENE':
            self.make_scene_empty()
            bpy.ops.wm.save_as_mainfile(filepath=save_path)
            bpy.ops.wm.open_mainfile(filepath=save_path)

        elif self.empty_mode == 'COPY_CURRENT':  # ← 여기가 고쳐진 부분!
            bpy.ops.wm.save_as_mainfile(filepath=save_path)
            bpy.ops.wm.open_mainfile(filepath=save_path)

        return {'FINISHED'}


    def handle_open_asset(self, context):
        import os
        import bpy

        tool = context.scene.ldv_browser_tool
        project, category, asset, version = tool.project, tool.category, tool.asset_enum, tool.version_enum

        if version == "LATEST":
            blend_file = get_project_publish_blend_path(project, category, asset)
        else:
            blend_file = os.path.join(get_project_blend_dir(project, category, asset), version)

        bpy.ops.wm.open_mainfile(filepath=blend_file)
        return {'FINISHED'}

    def handle_publish(self, context):
        import os
        import bpy

        source_path = bpy.data.filepath
        if not source_path:
            self.report({'ERROR'}, "먼저 파일을 저장해 주세요.")
            return {'CANCELLED'}

        # 현재 열린 파일 기준으로 에셋 정보 추출
        assets, category = get_assets()
        if not assets or not category:
            self.report({'ERROR'}, "현재 열린 파일에서 에셋 정보를 추출할 수 없습니다.")
            return {'CANCELLED'}
        asset = assets[0][0]

        # ✅ 퍼블리시 전 LookDev 요소 정리
        try:
            bpy.ops.object.sf_delete_lookdev_light_operator()
            print("[PUBLISH] sf_delete_lookdev_light_operator 호출 완료")
        except Exception as e:
            print(f"[WARN] LookDev 삭제 실패 (무시됨): {e}")

        # 경로 설정
        project_path = get_project_path()
        prefix = get_project_prefix()
        if prefix == "coc":
            main_dst = os.path.join(project_path, asset, "mod", f"{asset}.blend")
            backup_dst = os.path.join("U:/coc", asset, f"{asset}.blend")
        else:
            main_dst = os.path.join(project_path, "assets", category, asset, "mod", f"{asset}.blend")
            backup_dst = os.path.join(f"U:/{prefix}/assets", category, asset, f"{asset}.blend")

        os.makedirs(os.path.normpath(os.path.dirname(main_dst)), exist_ok=True)
        os.makedirs(os.path.normpath(os.path.dirname(backup_dst)), exist_ok=True)


        try:
            # 퍼블리시 저장 (현재 세션은 유지, copy=True)
            bpy.ops.wm.save_as_mainfile(filepath=main_dst,   copy=True, check_existing=False)
            bpy.ops.wm.save_as_mainfile(filepath=backup_dst, copy=True, check_existing=False)

            self.report({'INFO'}, f"퍼블리시 완료 ✅\n- {main_dst}\n- {backup_dst}")
        except Exception as e:
            self.report({'ERROR'}, f"퍼블리시 실패: {e}")
            return {'CANCELLED'}

        return {'FINISHED'}





    def make_scene_empty(self):
        import bpy

        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)

        def clean_data_blocks():
            data_types = [
                bpy.data.meshes,
                bpy.data.materials,
                bpy.data.images,
                bpy.data.cameras,
                bpy.data.lights,
                bpy.data.curves,
                bpy.data.armatures,
                bpy.data.textures,
                bpy.data.grease_pencils,
            ]
            for data_block in data_types:
                for item in data_block:
                    if item.users == 0:
                        data_block.remove(item)

        clean_data_blocks()
    def handle_save_incremental(self, context):
        bpy.ops.ldv.save_incremental()
        return {'FINISHED'}

    def invoke(self, context, event):
        if self.action == 'open_empty':
            return context.window_manager.invoke_props_dialog(self, width=400)
        return context.window_manager.invoke_confirm(self, event)

    def draw(self, context):
        if self.action == 'open_empty':
            self.layout.label(text="Choose Empty Mode:")
            self.layout.prop(self, "empty_mode", expand=True)
        else:
            self.layout.label(text=f"Proceed with '{self.action.replace('_', ' ').title()}'?")


# 어셋 데이터 구조
asset_cache = {
    "categories": ['bg', 'prop', 'ch'],
    "assets": {}
}


AUTO_KEYWORDS = {
    "skin": "MI_skin",
    "body": "MI_skin",
    "face": "MI_skin",
    "hair": "MI_hair",
    "eyebrow": "MI_eyeBrow",
    "eyeball": "MI_eyeBall",
    "teeth": "MI_teeth",
    "eyewhite": "MI_eyeWhite",
    "cornea": "MI_cornea",
}

def get_auto_target_mat(name):
    lname = name.lower()
    for keyword, mat_name in AUTO_KEYWORDS.items():
        if keyword in lname:
            return mat_name
    return "MI_cloth"

class SF_OT_PopupWarning(bpy.types.Operator):
    bl_idname = "wm.popup_warning"
    bl_label = "Warning"

    message: bpy.props.StringProperty()

    def execute(self, context):
        return {'FINISHED'}

    def invoke(self, context, event):
        msg = self.message  # ✅ 클로저로 캡처

        def draw(self, context):
            self.layout.label(text=msg)  # ✅ 여기는 self = UI 영역

        context.window_manager.popup_menu(draw, title="경고", icon='ERROR')
        return {'FINISHED'}

def cleanup_unused_data_except_materials():
    visible_objects = {obj.name for obj in bpy.context.view_layer.objects}

    # View Layer에 없는 오브젝트 제거
    for obj in list(bpy.data.objects):
        if obj.name not in visible_objects:
            bpy.data.objects.remove(obj, do_unlink=True)

    # 사용되지 않는 데이터 제거 (메터리얼 제외)
    def cleanup(data_block):
        for datablock in list(data_block):
            if datablock.users == 0:
                data_block.remove(datablock)

    cleanup(bpy.data.meshes)
    cleanup(bpy.data.armatures)
    cleanup(bpy.data.collections)
    cleanup(bpy.data.lights)
    cleanup(bpy.data.cameras)
    cleanup(bpy.data.curves)
    cleanup(bpy.data.images)
    cleanup(bpy.data.actions)
    cleanup(bpy.data.node_groups)
    
def add_driver_to_material(mat, node, prop_name, default, prop_type, input_idx, light_obj):
    try:
        if input_idx >= len(node.inputs):
            print(f"[SKIP] 노드 인덱스 {input_idx}가 유효하지 않습니다.")
            return

        node_input = node.inputs[input_idx]
        path_base = f'nodes["{node.name}"].inputs[{input_idx}].default_value'

        # 속성 초기화
        if prop_name not in light_obj:
            if prop_type == "COLOR":
                light_obj[prop_name] = [1.0, 1.0, 1.0, 1.0]
            elif prop_type == "VALUE":
                light_obj[prop_name] = default

        if prop_type == "COLOR":
            for i in range(4):  # RGBA
                fcurve = mat.node_tree.driver_add(path_base, i)
                driver = fcurve.driver
                driver.type = 'AVERAGE'
                while driver.variables:
                    driver.variables.remove(driver.variables[0])
                var = driver.variables.new()
                var.name = "var"
                var.type = 'SINGLE_PROP'
                var.targets[0].id_type = 'OBJECT'
                var.targets[0].id = light_obj
                var.targets[0].data_path = f'["{prop_name}"][{i}]'

        elif prop_type == "VALUE":
            fcurve = mat.node_tree.driver_add(path_base)
            driver = fcurve.driver
            driver.type = 'AVERAGE'
            while driver.variables:
                driver.variables.remove(driver.variables[0])
            var = driver.variables.new()
            var.name = "var"
            var.type = 'SINGLE_PROP'
            var.targets[0].id_type = 'OBJECT'
            var.targets[0].id = light_obj
            var.targets[0].data_path = f'["{prop_name}"]'

        bpy.context.view_layer.update()
        bpy.context.evaluated_depsgraph_get().update()
        print(f"[✔] 드라이버 연결됨: {mat.name} → {node.name} input[{input_idx}]")

    except Exception as e:
        print(f"[ERROR] 드라이버 연결 실패: {e}")

class SF_OT_ApplyLookdevMaterial(bpy.types.Operator):
    bl_idname = "sf.apply_lookdev_material"
    bl_label = "Apply LookDev Material"
    bl_description = "선택한 메터리얼을 선택된 오브젝트에 새로운 슬롯으로 추가합니다"

    def execute(self, context):
        selected = context.scene.sf_mat_switcher.mat_choices
        blend_path = resolve_script_path("blend", "ldvLight_v03.blend")

        if selected.lower() == "auto all":
            self.report({'WARNING'}, "'Auto All'은 이 기능에서 사용할 수 없습니다.")
            return {'CANCELLED'}

        # Step 1: 외부 .blend에서 메터리얼 로드 시도
        with bpy.data.libraries.load(blend_path, link=False) as (data_from, data_to):
            available = [name for name in data_from.materials]
            if selected not in available:
                self.report({'ERROR'}, f"{selected} 메터리얼이 blend 파일에 없습니다.")
                return {'CANCELLED'}
            data_to.materials = [selected]

        # Step 2: 실제 로드된 메터리얼 객체 확보
        src_mat = bpy.data.materials.get(selected)
        if not src_mat:
            self.report({'ERROR'}, f"{selected} 메터리얼 로드 실패.")
            return {'CANCELLED'}

        # Step 3: 선택된 오브젝트에 메터리얼 추가
        added_count = 0
        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue

            slot_names = [slot.material.name for slot in obj.material_slots if slot.material]
            if selected not in slot_names:
                obj.data.materials.append(src_mat)
                added_count += 1

        self.report({'INFO'}, f"{added_count}개의 오브젝트에 '{selected}' 메터리얼 슬롯 추가 완료")
        return {'FINISHED'}

def apply_auto_materials_ch(target_objects, blend_path, asset_name, category):
    needed = set()
    target_map = {}

    # 어떤 메터리얼이 필요한지 파악
    for obj in target_objects:
        if obj.type != 'MESH':
            continue

        for slot in obj.material_slots:
            mat = slot.material
            if not mat:
                continue
            orig_name = mat.name
            target = get_auto_target_mat(orig_name)
            target_map[orig_name] = target
            needed.add(target)

    # 필요한 메터리얼 로드
    with bpy.data.libraries.load(blend_path, link=False) as (data_from, data_to):
        for mat in needed:
            match = next((m for m in data_from.materials if m.lower() == mat.lower()), None)
            if match:
                data_to.materials.append(match)

    # 적용
    loaded_mats = {
        mat.name.lower(): mat for mat in bpy.data.materials
        if mat.name.lower() in [n.lower() for n in needed]
    }

    replaced_count = 0
    for obj in target_objects:
        if obj.type != 'MESH':
            continue

        for i, slot in enumerate(obj.material_slots):
            old_mat = slot.material
            if not old_mat:
                continue

            orig_name = old_mat.name
            target_key = target_map.get(orig_name)
            target_src_mat = loaded_mats.get(target_key.lower())

            if not target_src_mat:
                continue

            slot.material = None
            if old_mat.users == 0:
                bpy.data.materials.remove(old_mat)

            new_mat = target_src_mat.copy()
            new_mat.use_nodes = True
            new_mat.name = orig_name
            new_mat["applied_from"] = target_key
            slot.material = new_mat
            replaced_count += 1

            # 드라이버
            light_obj = find_light_object()
            if light_obj:
                for node in new_mat.node_tree.nodes:
                    if node.type == "GROUP" and node.node_tree and node.node_tree.name == "SF_Toon_v03":
                        for idx, inp in enumerate(node.inputs):
                            label = inp.name
                            if label == "Ambient Color":
                                add_driver_to_material(new_mat, node, "P01_Ambient_Color", (1,1,1,1), "COLOR", idx, light_obj)
                            elif label == "Shadow Color":
                                add_driver_to_material(new_mat, node, "P02_Shadow_Color", (1,1,1,1), "COLOR", idx, light_obj)
                            elif label == "Line Thickness":
                                add_driver_to_material(new_mat, node, "P30_Line_Thickness", 0.1, "VALUE", idx, light_obj)

    deduplicate_materials()
    apply_textures_from_json_ch(asset_name)
    return replaced_count


def apply_auto_materials(target_objects):
    blend_path = resolve_script_path("blend", "SF_Paint.blend")
    material_name = "MI_Paint"

    with bpy.data.libraries.load(blend_path, link=False) as (data_from, data_to):
        if material_name in data_from.materials:
            data_to.materials = [material_name]
        else:
            print(f"[ERROR] '{material_name}' not found in blend file.")
            return 0

    src_mat = bpy.data.materials.get(material_name)
    if not src_mat:
        print(f"[ERROR] '{material_name}' failed to load.")
        return 0

    count = 0
    for obj in target_objects:
        if obj.type != 'MESH':
            continue

        for slot in obj.material_slots:
            old_mat = slot.material
            if not old_mat:
                continue

            orig_name = old_mat.name
            slot.material = None

            # ❗ 반드시 먼저 삭제하고
            if old_mat.users == 0:
                bpy.data.materials.remove(old_mat)

            # ❗ 그 다음 복사하고 이름 지정
            new_mat = src_mat.copy()
            new_mat.use_nodes = True
            new_mat.name = orig_name
            new_mat["applied_from"] = material_name

            slot.material = new_mat
            count += 1
            
    deduplicate_materials()
    print(f"[OK] '{material_name}' applied to {count} slots without .001 issues.")
    return count






    
def find_light_object():
    for ob in bpy.context.scene.objects:
        if ob.type == "LIGHT" and "_light" in ob.name:
            return ob
    return None


def deduplicate_materials():
    """
    .001, .002 등의 중복 메터리얼을 정리하고,
    동일한 이름의 원본 메터리얼이 있으면 교체 후 제거합니다.
    """
    materials = bpy.data.materials
    name_map = {mat.name.split(".")[0]: mat for mat in materials if "." not in mat.name}

    for mat in list(materials):
        if "." in mat.name:
            base_name = mat.name.split(".")[0]
            if base_name in name_map:
                base_mat = name_map[base_name]
                for obj in bpy.data.objects:
                    if obj.type != 'MESH':
                        continue
                    for slot in obj.material_slots:
                        if slot.material == mat:
                            slot.material = base_mat
                if mat.users == 0:
                    bpy.data.materials.remove(mat)






def get_project_path():
    filepath = bpy.data.filepath.replace("\\", "/")
    # print(f"[DEBUG] 현재 파일 경로: {filepath}")

    if not filepath:
        # print("⚠️ [DEBUG] 블렌더 파일이 저장되지 않았습니다.")
        return ""

    path_parts = filepath.split("/")
    # print(f"[DEBUG] 경로 파츠: {path_parts}")

    if len(path_parts) < 1:
        # print("⚠️ [DEBUG] 경로 분석 실패")
        return ""

    coc_root = PROJECTS[COC_PROJECT][1].replace("\\", "/").rstrip("/")
    if filepath.lower().startswith(coc_root.lower() + "/"):
        return PROJECTS[COC_PROJECT][1]

    drive = path_parts[0]
    project_path = drive + "/"
    # print(f"[DEBUG] 추출된 프로젝트 경로: {project_path}")

    return project_path


def get_project_prefix():
    filepath = bpy.data.filepath.replace("\\", "/")
    if not filepath:
        return ""
    coc_root = PROJECTS[COC_PROJECT][1].replace("\\", "/").rstrip("/")
    if filepath.lower().startswith(coc_root.lower() + "/"):
        return "coc"
    drive = filepath.split("/")[0].upper()
    prefix_map = {
        "B:": "bts",
        "T:": "ttm",
        "A:": "ab",
        "S:": "dsc",
        "Z:": "FUZZ",
        "K:": "ckr"
    }
    return prefix_map.get(drive, "")

def rename_blender_scene(asset_name):
    prefix = get_project_prefix()
    if not prefix or not asset_name:
        print("⚠️ 접두어나 에셋 이름이 누락되었습니다.")
        return

    new_scene_name = f"{prefix}_{asset_name}"

    scene = bpy.context.scene
    print(f"🛠 기존 씬 이름: {scene.name}")
    scene.name = new_scene_name
    print(f"✅ 씬 이름이 변경됨: {scene.name}")
    
def get_ui_assets():  # 상단 버튼 전용
    tool = bpy.context.scene.ldv_browser_tool
    return [(tool.asset_enum, tool.asset_enum, "")], tool.category

def get_assets():
    filepath = bpy.data.filepath.replace("\\", "/")
    if not filepath:
        return None, None

    coc_root = PROJECTS[COC_PROJECT][1].replace("\\", "/").rstrip("/")
    if filepath.lower().startswith(coc_root.lower() + "/"):
        rel_parts = filepath[len(coc_root):].strip("/").split("/")
        if rel_parts and rel_parts[0]:
            return [(rel_parts[0], rel_parts[0], "")], COC_CATEGORY
        return None, None

    parts = filepath.split("/")
    try:
        assets_index = parts.index("assets")
        category = parts[assets_index + 1]
        asset_name = parts[assets_index + 2]
    except (ValueError, IndexError):
        return None, None

    return [(asset_name, asset_name, "")], category


def get_current_scene_asset_name():
    assets, _category = get_assets()
    if assets and assets[0]:
        return assets[0][0]

    filepath = bpy.data.filepath.replace("\\", "/")
    if not filepath:
        return ""

    filename = os.path.splitext(os.path.basename(filepath))[0]
    return filename.split("_")[0]


######################################################################################
import bpy, os
from datetime import datetime

# ------------------------------------------------------------
# 🔹 EEVEE 엔진 이름 감지 (4.1 ~ 4.5)
# ------------------------------------------------------------
def get_eevee_engine_name():
    render_prop = bpy.types.RenderSettings.bl_rna.properties.get("engine")
    if render_prop:
        enum_ids = {item.identifier for item in render_prop.enum_items}
        if 'BLENDER_EEVEE_NEXT' in enum_ids:
            return 'BLENDER_EEVEE_NEXT'
        if 'BLENDER_EEVEE' in enum_ids:
            return 'BLENDER_EEVEE'
    return 'BLENDER_EEVEE'


# ------------------------------------------------------------
# 🔹 EEVEE 버전별 기본 세팅
# ------------------------------------------------------------
def configure_eevee_for_version(scene):
    eevee = scene.eevee
    render = scene.render
    major, minor = bpy.app.version[:2]

    if (major, minor) >= (4, 2):  # EEVEE Next (4.2+)
        if hasattr(eevee, "use_shadows"):
            eevee.use_shadows = True
        if hasattr(eevee, "shadow_ray_count"):
            eevee.shadow_ray_count = 1
        if hasattr(eevee, "shadow_step_count"):
            eevee.shadow_step_count = 6
        if hasattr(eevee, "shadow_resolution_scale"):
            eevee.shadow_resolution_scale = 1.0
        if hasattr(eevee, "use_raytracing"):
            eevee.use_raytracing = True
        if hasattr(eevee, "use_fast_gi"):
            eevee.use_fast_gi = True
        if hasattr(eevee, "use_taa_reprojection"):
            eevee.use_taa_reprojection = True
        eevee.taa_samples = 16
        eevee.taa_render_samples = 64
        eevee.light_threshold = 0.01
        if hasattr(eevee, "ray_tracing_options"):
            eevee.ray_tracing_options.use_denoise = True
        if hasattr(eevee, "use_ssr"):
            eevee.use_ssr = True
        if hasattr(eevee, "use_ssr_refraction"):
            eevee.use_ssr_refraction = True
        if hasattr(eevee, "use_bloom"):
            eevee.use_bloom = True
            eevee.bloom_intensity = 0.02
        if hasattr(eevee, "use_gtao"):
            eevee.use_gtao = True
        if hasattr(eevee, "use_gtao_bent_normals"):
            eevee.use_gtao_bent_normals = True
        if hasattr(eevee, "use_gtao_bounce"):
            eevee.use_gtao_bounce = True

        render.resolution_x = 2048
        render.resolution_y = 2048
        render.use_simplify = True
        render.simplify_subdivision = 1
        render.film_transparent = True
        scene.view_settings.view_transform = 'Standard'

    else:  # Legacy EEVEE (4.1 이하)
        eevee.use_gtao = True
        eevee.gtao_distance = 0.2
        eevee.gtao_factor = 1.0
        eevee.gtao_quality = 0.25
        eevee.shadow_cube_size = '4096'
        eevee.shadow_cascade_size = '4096'
        if hasattr(eevee, "use_shadow_high_bitdepth"):
            eevee.use_shadow_high_bitdepth = True
        eevee.use_soft_shadows = True
        eevee.use_bloom = False
        eevee.use_ssr = True
        eevee.use_ssr_refraction = True
        eevee.taa_render_samples = 64
        scene.view_settings.view_transform = 'Standard'
        render.resolution_x = 2048
        render.resolution_y = 2048


# ------------------------------------------------------------
# 🔹 캐릭터 전용 EEVEE 세팅
# ------------------------------------------------------------
def configure_eevee_for_characters(scene):
    eevee = scene.eevee
    render = scene.render
    major, minor = bpy.app.version[:2]

    if (major, minor) >= (4, 2):  # EEVEE Next (Blender 4.2+)
        # --- AO / Shadows ---
        if hasattr(eevee, "use_shadows"):
            eevee.use_shadows = True
        if hasattr(eevee, "use_gtao"):
            eevee.use_gtao = True
        if hasattr(eevee, "use_gtao_bent_normals"):
            eevee.use_gtao_bent_normals = True
        if hasattr(eevee, "use_gtao_bounce"):
            eevee.use_gtao_bounce = True

        # --- Raytracing / GI ---
        if hasattr(eevee, "use_raytracing"):
            eevee.use_raytracing = True
        if hasattr(eevee, "use_fast_gi"):
            eevee.use_fast_gi = True

        # --- Sampling ---
        if hasattr(eevee, "use_taa_reprojection"):
            eevee.use_taa_reprojection = True
        eevee.taa_samples = 16
        eevee.taa_render_samples = 64
        eevee.light_threshold = 0.01

        # --- Bloom / SSR ---
        if hasattr(eevee, "use_bloom"):
            eevee.use_bloom = True
            eevee.bloom_intensity = 0.02
        if hasattr(eevee, "use_ssr"):
            eevee.use_ssr = True
        if hasattr(eevee, "use_ssr_refraction"):
            eevee.use_ssr_refraction = True

        # --- Render settings ---
        render.resolution_x = 2048
        render.resolution_y = 2048
        render.use_simplify = True
        render.simplify_subdivision = 1
        render.film_transparent = True

        # --- View transform (Goo Engine check) ---
        if "goo" in bpy.app.version_string.lower():
            scene.view_settings.view_transform = 'Standard'
        else:
            scene.view_settings.view_transform = 'Khronos PBR Neutral'

    else:
        # --- Legacy EEVEE (4.1 이하) ---
        eevee.use_gtao = True
        eevee.gtao_distance = 0.2
        eevee.gtao_factor = 1.0
        eevee.gtao_quality = 0.25
        eevee.shadow_cube_size = '4096'
        eevee.shadow_cascade_size = '4096'
        eevee.use_shadow_high_bitdepth = True
        eevee.use_soft_shadows = True
        eevee.use_bloom = False
        eevee.use_ssr = True
        eevee.use_ssr_refraction = True
        eevee.taa_samples = 16
        eevee.taa_render_samples = 64

        # --- Render settings ---
        render.resolution_x = 2048
        render.resolution_y = 2048
        scene.render.film_transparent = True

        # --- View transform (Goo Engine check) ---
        if "goo" in bpy.app.version_string.lower():
            scene.view_settings.view_transform = 'Standard'
        else:
            scene.view_settings.view_transform = 'Khronos PBR Neutral'

        


# ------------------------------------------------------------
# 🔹 Build Scene Operator (4.1~4.5 통합)
# ------------------------------------------------------------
class SF_OT_BuildSceneOperator(bpy.types.Operator):
    bl_idname = "object.sf_build_scene_operator"
    bl_label = "Build Scene"

    def execute(self, context):
        tool = context.scene.ldv_browser_tool
        asset_name = tool.asset_enum
        category = tool.category

        if not asset_name or asset_name == "NONE":
            self.report({'ERROR'}, "UI에서 어셋을 선택해 주세요")
            return {'CANCELLED'}

        bpy.ops.sf.cleanup_orphans_combined()
        self.remove_empty_collections()
        sc = context.scene
        default_collection = sc.collection

        category_col_name = f"{category}_col"
        asset_col_name = f"{asset_name}_col"

        # --- 컬렉션 구조 ---
        category_col = bpy.data.collections.get(category_col_name)
        if not category_col:
            category_col = bpy.data.collections.new(category_col_name)
        if category_col.name not in default_collection.children:
            default_collection.children.link(category_col)

        asset_col = bpy.data.collections.get(asset_col_name)
        if not asset_col:
            asset_col = bpy.data.collections.new(asset_col_name)
        if asset_col.name not in category_col.children:
            category_col.children.link(asset_col)

        for obj in bpy.context.selected_objects:
            for col in obj.users_collection:
                col.objects.unlink(obj)
            asset_col.objects.link(obj)

        # --- 날짜 기반 아웃풋 경로 ---
        project_path = get_project_path()
        if get_project_prefix() == "coc":
            output_path = get_coc_render_output_dir(asset_name)
        else:
            today = datetime.now().strftime("%y%m%d")
            output_path = os.path.join(project_path, "output", "ldv", asset_name, today)
        os.makedirs(output_path, exist_ok=True)
        sc.render.filepath = os.path.join(output_path, "")
        self.report({'INFO'}, f"[Build] Output path set to: {sc.render.filepath}")

        # --- 렌더 엔진 설정 ---
        if is_goo_engine():
            sc.render.engine = get_eevee_engine_name()
            configure_eevee_for_version(sc)
        elif category == "ch":
            sc.render.engine = get_eevee_engine_name()
            configure_eevee_for_characters(sc)
        else:
            sc.render.engine = 'CYCLES'
            configure_cycles_for_background(sc)

        # --- geo_empty 정리 ---
        for obj in bpy.data.objects:
            if obj.name.startswith("geo") and obj.type == 'EMPTY':
                top_node = obj
                while top_node.parent and top_node.parent.type == 'EMPTY':
                    top_node = top_node.parent
                objs_to_move = [top_node] + list(top_node.children_recursive)
                for obj_to_move in objs_to_move:
                    if obj_to_move.name in bpy.context.view_layer.objects:
                        bpy.context.view_layer.objects.active = obj_to_move
                        obj_to_move.select_set(True)
                for selected_obj in bpy.context.selected_objects:
                    for other_col in selected_obj.users_collection:
                        other_col.objects.unlink(selected_obj)
                    if selected_obj.name not in asset_col.objects:
                        asset_col.objects.link(selected_obj)

        rename_blender_scene(asset_name)
        self.report({'INFO'}, "Scene build completed (non-destructive)")
        return {'FINISHED'}

    def remove_empty_collections(self):
        def is_empty(collection):
            return not collection.objects and not any(child.objects for child in collection.children)
        for collection in list(bpy.data.collections):
            if is_empty(collection):
                bpy.data.collections.remove(collection)


class SF_OT_SetCharacterLightAndOutline(bpy.types.Operator):
    bl_idname = "object.set_character_light_and_outline"
    bl_label = "Set Character Light & Outline"
    bl_description = "캐릭터용: 라이트 세팅 및 Outline 머티리얼 설정"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.object

        # 1. 선택된 오브젝트가 라이트일 경우 라이트 세팅 적용
        if obj and obj.type == 'LIGHT':
            light_data = obj.data
            try:
                if hasattr(light_data, "use_contact_shadow"):
                    light_data.use_contact_shadow = False
                if hasattr(light_data, "shadow_cascade_max_distance"):
                    light_data.shadow_cascade_max_distance = 10.0
                if hasattr(light_data, "shadow_buffer_bias"):
                    light_data.shadow_buffer_bias = 0.03

                obj.rotation_euler[0] = 0.526
                self.report({'INFO'}, f"라이트 세팅 완료: {obj.name}")
            except Exception as e:
                self.report({'WARNING'}, f"라이트 세팅 실패: {e}")

        # 2. 씬의 모든 머티리얼 중 SF_Outline* 찾기 (대소문자 무시)
        for mat in bpy.data.materials:
            if mat.name.lower().startswith("sf_outline"):
                if hasattr(mat, "shadow_method"):
                    mat.shadow_method = 'NONE'
                    self.report({'INFO'}, f"Outline 머티리얼 수정: {mat.name}")

        return {'FINISHED'}   # ✅ 반드시 set 타입으로 리턴




        
# def configure_eevee_for_characters(scene):
    # eevee = scene.eevee
    # render = scene.render

    # # EEVEE 옵션 설정
    # eevee.use_gtao = True
    # eevee.gtao_distance = 0.2
    # eevee.gtao_factor = 1.0
    # eevee.gtao_quality = 0.25
    # eevee.shadow_cube_size = '4096'
    # eevee.shadow_cascade_size = '4096'
    # eevee.use_shadow_high_bitdepth = True
    # eevee.use_soft_shadows = True
    # eevee.use_bloom = False
    # eevee.use_ssr = True
    # eevee.use_ssr_refraction = True
    # eevee.taa_samples = 16                  # ✅ 뷰포트용
    # eevee.taa_render_samples = 64           # ✅ 렌더용

    # # 렌더 해상도
    # render.resolution_x = 2048
    # render.resolution_y = 2048

    # # 배경 투명 여부 (선택)
    # scene.render.film_transparent = True

    # # 컬러 뷰 트랜스폼
    # if "goo" in bpy.app.version_string.lower():
        # scene.view_settings.view_transform = 'Standard'
    # else:
        # scene.view_settings.view_transform = 'Khronos PBR Neutral'


def configure_cycles_for_background(scene):
    cycles = scene.cycles
    render = scene.render

    # Cycles 설정
    cycles.device = 'GPU'
    cycles.max_bounces = 8
    cycles.diffuse_bounces = 3
    cycles.glossy_bounces = 3
    cycles.transmission_bounces = 5
    cycles.volume_bounces = 2
    cycles.transparent_max_bounces = 20

    cycles.samples = 64
    cycles.preview_samples = 16
    cycles.preview_adaptive_threshold = 1

    cycles.use_denoising = True
    cycles.denoising_input_passes = 'RGB_ALBEDO_NORMAL'
    cycles.use_preview_denoising = True
    cycles.preview_denoising_input_passes = 'RGB_ALBEDO_NORMAL'
    cycles.denoiser = 'OPENIMAGEDENOISE'
    cycles.denoising_use_gpu = True

    # 렌더 설정
    render.use_simplify = True
    render.simplify_subdivision = 2
    render.resolution_x = 2048
    render.resolution_y = 2048
    render.film_transparent = True

    # 뷰 트랜스폼 설정
    if "goo" in bpy.app.version_string.lower():
        scene.view_settings.view_transform = 'Standard'
    else:
        scene.view_settings.view_transform = 'Khronos PBR Neutral'




def copy_outline_from_existing(source_obj, target_obj):
    outline_mod = next((m for m in source_obj.modifiers if m.name == "SF_Outline"), None)
    if not outline_mod:
        return

    new_mod = target_obj.modifiers.new(name="SF_Outline", type=outline_mod.type)
    for attr in dir(outline_mod):
        if not attr.startswith("_") and hasattr(new_mod, attr):
            try:
                setattr(new_mod, attr, getattr(outline_mod, attr))
            except:
                pass

    outline_mats = [mat for mat in source_obj.data.materials if mat and mat.name.startswith("SF_Outline_")]
    if not outline_mats:
        return

    outline_mat = outline_mats[0]
    if outline_mat.name not in [m.name for m in target_obj.data.materials if m]:
        target_obj.data.materials.append(outline_mat)

    mat_slots = list(target_obj.data.materials)
    index = mat_slots.index(outline_mat)
    if index != 0:
        mat_slots.insert(0, mat_slots.pop(index))
        target_obj.data.materials.clear()
        for m in mat_slots:
            target_obj.data.materials.append(m)





class ChangeTextureNodeColorSpaceOperator(bpy.types.Operator):
    """Change color space of all texture nodes to Filmic sRGB"""
    bl_idname = "material.change_texture_node_color_space"
    bl_label = "Change Texture Node Color Space"

    def execute(self, context):
        # 모든 이미지를 검색합니다.
        for img in bpy.data.images:
            print(f"Processing image {img.name}...")
            # 컬러 스페이스가 'Non-Color'가 아니면
            if img.colorspace_settings.name != 'Non-Color':
                print(f"Image {img.name} has color space {img.colorspace_settings.name}. Changing to Filmic sRGB...")
                # 컬러 스페이스를 'Filmic sRGB'로 변경합니다.
                img.colorspace_settings.name = 'Filmic sRGB'
                self.report({'INFO'}, f"Updated color space of image {img.name} to Filmic sRGB.")
        return {'FINISHED'}
        
 
       
class OBJECT_OT_SetVertexColor(bpy.types.Operator):
    bl_idname = "object.set_vertex_color"
    bl_label = "Set Line Color to Selection"
    bl_options = {'REGISTER', 'UNDO'}

    # 사용자 정의 컬러 프로퍼티
    color: bpy.props.FloatVectorProperty(
        name="Color",
        subtype='COLOR',
        default=(0.2, 0.025, 0.02, 1.0),  # Alpha 값 추가
        min=0.0, max=1.0,
        size=4,  # size를 4로 설정하여 RGBA 형식을 사용하도록 함
        description="color picker"
    )

    def execute(self, context):
        # 스킨 컬러 RGBA 분해
        r, g, b, a = self.color

        # 선택된 모든 메쉬 오브젝트에 대해
        for obj in bpy.context.selected_objects:
            if obj.type == 'MESH':
                mesh = obj.data
                
                # 'Color.'로 시작하는 모든 컬러 어트리뷰트 제거
                for attr in list(mesh.color_attributes):
                    if attr.name.startswith("Color."):
                        mesh.color_attributes.remove(attr)

                # 'Color' 어트리뷰트가 이미 있다면 제거 후 재생성
                if "Color" in mesh.color_attributes:
                    mesh.color_attributes.remove(mesh.color_attributes["Color"])

                # 'Color' 어트리뷰트 생성 및 스킨 컬러 적용
                bpy.context.view_layer.objects.active = obj
                bpy.ops.object.mode_set(mode='OBJECT')  # 오브젝트 모드로 변경
                bpy.ops.geometry.color_attribute_add(name="Color", domain='POINT', data_type='FLOAT_COLOR')
                color_attr = mesh.color_attributes.get("Color")

                # 생성된 'Color' 어트리뷰트에 스킨 컬러 적용
                if color_attr:
                    # 모든 버텍스에 스킨 컬러 적용
                    colors = [r, g, b, a] * len(mesh.vertices)
                    color_attr.data.foreach_set("color", colors)
                    mesh.update()

        return {'FINISHED'}
        
        

class OBJECT_OT_ApplySkinColor(bpy.types.Operator):
    """선택한 메쉬 오브젝트에 스킨 컬러 어트리뷰트 'Color' 적용 및 'Color.'로 시작하는 어트리뷰트 제거"""
    bl_idname = "object.apply_skin_color"
    bl_label = "Apply Skin Color"
    bl_options = {'REGISTER', 'UNDO'}

    # 사용자 정의 스킨 컬러 프로퍼티
    skin_color: bpy.props.FloatVectorProperty(
        name="Color",
        subtype='COLOR',
        default=(0.65, 0.2, 0.1, 1.0),  # RGBA
        min=0.0, max=1.0,
        size=4,
        description="Define the skin color"
    )

    def execute(self, context):
        # 스킨 컬러 RGBA 분해
        r, g, b, a = self.skin_color

        # 선택된 모든 메쉬 오브젝트에 대해
        for obj in bpy.context.selected_objects:
            if obj.type == 'MESH':
                mesh = obj.data
                
                # 'Color.'로 시작하는 모든 컬러 어트리뷰트 제거
                for attr in list(mesh.color_attributes):
                    if attr.name.startswith("Color."):
                        mesh.color_attributes.remove(attr)

                # 'Color' 어트리뷰트가 이미 있다면 제거 후 재생성
                if "Color" in mesh.color_attributes:
                    mesh.color_attributes.remove(mesh.color_attributes["Color"])

                # 'Color' 어트리뷰트 생성 및 스킨 컬러 적용
                bpy.context.view_layer.objects.active = obj
                bpy.ops.object.mode_set(mode='OBJECT')  # 오브젝트 모드로 변경
                bpy.ops.geometry.color_attribute_add(name="Color", domain='POINT', data_type='FLOAT_COLOR')
                color_attr = mesh.color_attributes.get("Color")

                # 생성된 'Color' 어트리뷰트에 스킨 컬러 적용
                if color_attr:
                    # 모든 버텍스에 스킨 컬러 적용
                    colors = [r, g, b, a] * len(mesh.vertices)
                    color_attr.data.foreach_set("color", colors)
                    mesh.update()
        return {'FINISHED'}


        
#########################################################################################################################

def perform_baking(obj, bake_type='DIFFUSE'):
    """
    Performs the baking operation on the selected object.
    """
    bpy.ops.object.bake(type=bake_type)
    obj.select_set(False)

def bake_mesh_objects_in_collection(collection_name, bake_type='DIFFUSE', target='VERTEX_COLORS', filepath=None):
    """
    Bakes mesh objects in a given collection.
    """
    if filepath:
        asset_name = get_asset_name_from_file(filepath)
    else:
        asset_name = get_asset_name_from_file(bpy.context.blend_data.filepath)
    collection = get_or_create_collection(f"{asset_name}_{collection_name}")
    if collection:
        for obj in [obj for obj in collection.objects if obj.type == 'MESH']:
            prepare_object_for_baking(obj, target)
            perform_baking(obj, bake_type)


####################################################################################################################################################################
# 파일을 여는 함수
def open_file(path):
    bpy.ops.wm.open_mainfile(filepath=path)


class SF_CleanupOrphansCombined2(bpy.types.Operator):
    bl_idname = "sf.cleanup_orphans_combined"
    bl_label = "Clean Up Orphans (Combined)"

    def execute(self, context):
        # 첫 번째 조건: 로컬 및 링크드 데이터 블록 모두 정리하지 않음
        bpy.ops.outliner.orphans_purge(do_recursive=True, do_local_ids=False, do_linked_ids=False)

        # 두 번째 조건: 로컬 데이터 블록만 정리
        bpy.ops.outliner.orphans_purge(do_recursive=True, do_local_ids=True, do_linked_ids=False)

        # 세 번째 조건: 링크드 데이터 블록만 정리
        bpy.ops.outliner.orphans_purge(do_recursive=True, do_local_ids=False, do_linked_ids=True)

        return {'FINISHED'}


class SF_OT_LookDevOperator(bpy.types.Operator):
    bl_idname = "object.sf_lookdev_operator"
    bl_label = "Reference Lookdev Light"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene

        # ✅ 이미 존재하면 불러오지 않음
        already_loaded = any(c.name.startswith("chLdv_Light") for c in bpy.data.collections)
        already_world = any(w.name.startswith("chLdv_world") for w in bpy.data.worlds)

        if already_loaded:
            self.report({'INFO'}, "chLdv_Light 컬렉션이 이미 존재합니다.")
        else:
            filepath = resolve_script_path("blend", "ldvLight_v03.blend")
            with bpy.data.libraries.load(filepath, link=False) as (data_from, data_to):
                data_to.collections = [name for name in data_from.collections if name == "chLdv_Light"]

            for coll in data_to.collections:
                # 먼저 다른 컬렉션에서 언링크
                for scene in bpy.data.scenes:
                    for parent in scene.collection.children:
                        if coll.name in parent.children:
                            parent.children.unlink(coll)

                # Scene Collection 하위로 링크
                context.scene.collection.children.link(coll)
                self.report({'INFO'}, f"{coll.name} 컬렉션 Scene Collection에 링크 완료")


        if already_world:
            self.report({'INFO'}, "chLdv_world 월드가 이미 존재합니다.")
        else:
            filepath = resolve_script_path("blend", "ldvLight_v03.blend")
            with bpy.data.libraries.load(filepath, link=False) as (data_from, data_to):
                data_to.worlds = [name for name in data_from.worlds if name == "chLdv_world"]

            for world in data_to.worlds:
                context.scene.world = world
                self.report({'INFO'}, f"{world.name} 월드 링크 완료")

        # ✅ 카메라는 덮어쓰기 가능 (존재 시 설정만)
        far_cam = next((obj for obj in bpy.data.objects if obj.name.startswith("FarCam") and obj.type == 'CAMERA'), None)
        if far_cam:
            context.scene.camera = far_cam
        else:
            self.report({'WARNING'}, "FarCam 카메라가 존재하지 않습니다.")
        try:
            bpy.ops.object.sf_parent_light_to_turntable()
        except Exception as e:
            print(f"[INFO] sf_parent_light_to_turntable failed (ignored): {e}")

        return {'FINISHED'}

class SF_OT_DeleteLookDevLightOperator(bpy.types.Operator):
    bl_idname = "object.sf_delete_lookdev_light_operator"
    bl_label = "Delete LookDev Light"

    def execute(self, context):
        deleted_any = False

        # 1. chLdv_Light로 시작하는 모든 컬렉션 삭제
        for coll in list(bpy.data.collections):
            if coll.name.startswith("chLdv_Light"):
                for scene in bpy.data.scenes:
                    if coll.name in scene.collection.children:
                        scene.collection.children.unlink(coll)
                name = coll.name  # 삭제 전에 저장
                bpy.data.collections.remove(coll)
                self.report({'INFO'}, f"컬렉션 삭제됨: {name}")
                deleted_any = True


        # 2. chLdv_world로 시작하는 모든 월드 삭제
        for world in list(bpy.data.worlds):
            if world.name.startswith("chLdv_world"):
                if context.scene.world == world:
                    context.scene.world = None
                name = world.name
                bpy.data.worlds.remove(world)
                self.report({'INFO'}, f"월드 삭제됨: {name}")
                deleted_any = True


        # 3. FarCam으로 시작하는 모든 카메라 삭제
        for obj in list(bpy.data.objects):
            if obj.name.startswith("FarCam") and obj.type == 'CAMERA':
                name = obj.name
                bpy.data.objects.remove(obj, do_unlink=True)
                self.report({'INFO'}, f"FarCam 삭제됨: {name}")
                deleted_any = True

        if not deleted_any:
            self.report({'WARNING'}, "삭제할 LookDev 요소가 없습니다")

        return {'FINISHED'}

def apply_matching_materials():
    materials = bpy.data.materials

    for obj in bpy.context.selected_objects:
        obj_data = obj.data
        if not obj_data or not hasattr(obj_data, "materials"):
            continue

        for i, slot in enumerate(obj.material_slots):
            material = slot.material
            if not material:
                continue

            # Step 1: 이름 교체 시도
            target_name = material.name.replace("MIA_", "MI_")

            # Step 2: 링크 네임스페이스 제거
            if ":" in target_name:
                target_name = target_name.split(":")[-1]

            # Step 3: .001 등 접미사 제거
            base_material_name = target_name.split(".")[0]

            # Step 4: 같은 이름 있으면 교체
            if base_material_name in materials:
                matched = materials[base_material_name]
                obj_data.materials[i] = matched
                print(f"[MATCH] {material.name} → {matched.name}")
            else:
                # 이름만 MI_로 변경
                if material.name.startswith("MIA_"):
                    new_name = "MI_" + material.name[4:]
                    if new_name not in materials:
                        print(f"[RENAME] {material.name} → {new_name}")
                        material.name = new_name
                    else:
                        print(f"[SKIP] {material.name} 이름 충돌 - 유지됨")
                
                
def load_browser_state(tool):
    # STATE_FILE = "C:/_json/ldv_browser_state.json"
    refresh_projects_from_pipeline()
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            state = json.load(f)
        saved_project = state.get("project", "")
        project_keys = list(PROJECTS.keys())
        if saved_project in project_keys:
            tool.project_index = project_keys.index(saved_project)
        else:
            tool.project_index = state.get("project_index", 0)
        clamp_project_index(tool)
        restored_category = state.get("category", "ch")
        tool.category = COC_CATEGORY if tool.project == COC_PROJECT else restored_category
        tool.asset_enum = state.get("asset_enum", "")
        try:
            tool.version_enum = state.get("version_enum", "LATEST")
        except Exception:
            pass
        print("[INFO] Browser state restored.")
    else:
        print("[INFO] No previous browser state file found.")


def sync_browser_state_to_current_file(tool, filepath=None, save_state=True):
    refresh_projects_from_pipeline()
    filepath = (bpy.data.filepath if filepath is None else filepath) or ""
    normalized_path = filepath.replace("\\", "/")
    if not normalized_path:
        return False

    matched_project = ""
    matched_root = ""
    for project_name, (_prefix, asset_root) in PROJECTS.items():
        root = str(asset_root or "").replace("\\", "/").rstrip("/")
        if root and normalized_path.lower().startswith(root.lower() + "/") and len(root) > len(matched_root):
            matched_project = project_name
            matched_root = root

    if not matched_project:
        return False

    project_keys = list(PROJECTS.keys())
    if matched_project in project_keys:
        tool.project_index = project_keys.index(matched_project)
        clamp_project_index(tool)

    rel_parts = [part for part in normalized_path[len(matched_root):].strip("/").split("/") if part]
    if matched_project == COC_PROJECT:
        if not rel_parts:
            return False
        asset_name = rel_parts[0]
        category = COC_CATEGORY
    else:
        if len(rel_parts) < 2:
            return False
        category = rel_parts[0]
        asset_name = rel_parts[1]

    tool.category = category
    tool.asset_enum = asset_name

    publish_path = get_project_publish_blend_path(matched_project, category, asset_name).replace("\\", "/")
    tool.version_enum = "LATEST" if normalized_path.lower() == publish_path.lower() else os.path.basename(filepath)

    if save_state:
        save_browser_state(tool)
    return True

# def find_socket_index(sockets, target_socket):
    # for i, sock in enumerate(sockets):
        # if sock.identifier == target_socket.identifier:
            # return i
    # return None

def load_image_cached(path):
    abspath = bpy.path.abspath(path)
    for img in bpy.data.images:
        if bpy.path.abspath(img.filepath) == abspath:
            return img
    return bpy.data.images.load(path)

def ensure_mi_paint_json_exists():
    import bpy
    import json
    import os

    json_path = resolve_script_path("blend", "MI_Paint.json")
    blend_path = resolve_script_path("blend", "SF_Paint.blend")

    if os.path.exists(json_path):
        print(f"[INFO] MI_Paint JSON already exists: {json_path}")
        return json_path

    with bpy.data.libraries.load(blend_path, link=False) as (data_from, data_to):
        if "MI_Paint" in data_from.materials:
            data_to.materials = ["MI_Paint"]
        else:
            print(f"[ERROR] MI_Paint not found in {blend_path}")
            return None

    mat = bpy.data.materials.get("MI_Paint")
    if not mat or not mat.use_nodes:
        print(f"[ERROR] MI_Paint failed to load or has no nodes.")
        return None

    data = {"name": mat.name, "nodes": [], "links": []}

    for node in mat.node_tree.nodes:
        node_data = {
            "name": node.name,
            "type": node.type,
            "location": list(node.location)
        }
        if node.type == 'GROUP' and node.node_tree:
            node_data["group_name"] = node.node_tree.name
        elif node.type == 'RGB':
            node_data["color"] = list(node.outputs[0].default_value)
        elif node.type == 'VALUE':
            node_data["value"] = node.outputs[0].default_value
        elif node.type == 'TEX_IMAGE' and node.image:
            node_data["image"] = bpy.path.abspath(node.image.filepath)
            node_data["colorspace"] = node.image.colorspace_settings.name
        data["nodes"].append(node_data)

    # 🚀 완전 강화: Blender 실제 소켓 이름 그대로 저장
    for link in mat.node_tree.links:
        data["links"].append({
            "from_node": link.from_node.name,
            "from_socket": link.from_socket.name,
            "from_type": link.from_socket.type,
            "to_node": link.to_node.name,
            "to_socket": link.to_socket.name,
            "to_type": link.to_socket.type
        })

    with open(json_path, 'w') as f:
        json.dump(data, f, indent=4)

    print(f"[SUCCESS] MI_Paint JSON created with exact socket names: {json_path}")
    return json_path


def load_material_json_data():
    blend_path = bpy.data.filepath
    if not blend_path:
        print("[ERROR] 씬 파일을 먼저 저장하세요!")
        return None, None, None, {}

    path_parts = blend_path.replace("\\", "/").split("/")
    if len(path_parts) < 6:
        print("[ERROR] 경로 구조가 예상과 다릅니다.")
        return None, None, None, {}

    drive, assets_dir, category = path_parts[0], path_parts[1], path_parts[2]
    filename_no_ext = os.path.splitext(os.path.basename(blend_path))[0]
    asset_name = filename_no_ext.split("_v")[0]
    json_path = f"{drive}/{assets_dir}/{category}/{asset_name}/mod/usd/{asset_name}.json"
    json_path = os.path.normpath(json_path)

    if not os.path.exists(json_path):
        print(f"[ERROR] JSON file not found: {json_path}")
        return None, None, None, {}

    try:
        with open(json_path, 'r') as f:
            data = json.load(f)
    except Exception as e:
        print(f"[ERROR] Failed to load JSON: {e}")
        return None, None, None, {}

    material_data = {}
    for mesh in data.get("meshes", []):
        for mat in mesh.get("materials", []):
            mat_name = mat.get("name")
            color = mat.get("color")
            diffuse_texture = mat.get("textures", {}).get("Diffuse")
            material_data[mat_name] = {
                "color": color,
                "diffuse_texture": diffuse_texture
            }

    return asset_name, category, json_path, material_data

# ---------------------------------------
# JSON 적용 함수
# ---------------------------------------
def apply_json_to_material():
    asset_name, category, json_path, _ = load_material_json_data()
    if not json_path or not os.path.exists(json_path):
        print("[ERROR] JSON 경로 없음")
        return

    with open(json_path, 'r') as f:
        data = json.load(f)

    for mesh in data.get("meshes", []):
        for mat_info in mesh.get("materials", []):
            name = mat_info.get("name")
            if not name:
                continue

            mat = bpy.data.materials.get(name)
            if not mat or not mat.use_nodes:
                continue

            nodes = mat.node_tree.nodes
            links = mat.node_tree.links

            # Diffuse Color
            color = mat_info.get("Diffuse")
            if color and isinstance(color, list) and len(color) in [3, 4]:
                diffuse_color = next((n for n in nodes if n.type == 'RGB' and n.name == "Diffuse Color"), None)
                if diffuse_color:
                    try:
                        diffuse_color.outputs[0].default_value = (*color[:3], 1.0)
                    except Exception as e:
                        print(f"[ERROR] Diffuse Color 적용 실패: {e}")
            elif color:
                print(f"[WARN] {name} → 잘못된 컬러값 형식: {color}")

            # Diffuse Texture
            textures = mat_info.get("textures", {})
            diffuse_path = textures.get("allTextures", [])
            if diffuse_path:
                tex_path = diffuse_path[0]
                try:
                    img = bpy.data.images.load(tex_path, check_existing=True)
                    tex_node = next((n for n in nodes if n.type == 'TEX_IMAGE' and n.name == "Diffuse Texture"), None)
                    if tex_node:
                        tex_node.image = img
                        tex_node.image.colorspace_settings.name = 'sRGB'
                except Exception as e:
                    print(f"[ERROR] Diffuse 텍스처 로드 실패: {tex_path} ({e})")

            # Mix Fac
            mix_node = next((n for n in nodes if n.name == "Diffuse Mix"), None)
            if mix_node:
                mix_node.inputs[0].default_value = 1.0 if diffuse_path else 0.0

            # Normal Texture
            normal_path = mat_info.get("Normal")
            if normal_path:
                try:
                    img = bpy.data.images.load(normal_path, check_existing=True)
                    normal_tex = next((n for n in nodes if n.type == 'TEX_IMAGE' and n.name == "Normal Texture"), None)
                    normal_map = next((n for n in nodes if n.type == 'NORMAL_MAP'), None)
                    group = next((n for n in nodes if n.name == "Group.002"), None)

                    if normal_tex:
                        normal_tex.image = img
                        normal_tex.image.colorspace_settings.name = 'Non-Color'                                                                            

                    if normal_tex and normal_map:
                        links.new(normal_tex.outputs["Color"], normal_map.inputs["Color"])
                    if normal_map and group:
                        links.new(normal_map.outputs["Normal"], group.inputs["Normal"])
                except Exception as e:
                    print(f"[ERROR] Normal 텍스처 로드 실패: {normal_path} ({e})")
                    
class SF_OT_ConvertToPaintShader(bpy.types.Operator):
    bl_idname = "object.sf_convert_to_paint_shader"
    bl_label = "Convert Shader (MI_Paint 기반)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        import re

        def extract_clean_base_name(name: str) -> str:
            name = re.sub(r'_tmp(_\d+)?$', '', name)     # _tmp 또는 _tmp_숫자 제거
            name = re.sub(r'\.\d{3}$', '', name)         # .001 등 Blender suffix 제거
            return name

        def convert_to_paint_shader(target_mat: bpy.types.Material):
            blend_path = resolve_script_path("blend", "SF_Paint.blend")
            src_name = "MI_Paint"

            # MI_Paint가 없으면 로드
            if src_name not in bpy.data.materials:
                with bpy.data.libraries.load(blend_path, link=False) as (data_from, data_to):
                    if src_name in data_from.materials:
                        data_to.materials = [src_name]

            src_mat = bpy.data.materials.get(src_name)
            if not src_mat:
                return False

            # 노드 복사
            target_mat.use_nodes = True
            target_nodes = target_mat.node_tree
            target_nodes.nodes.clear()

            for node in src_mat.node_tree.nodes:
                new_node = target_nodes.nodes.new(type=node.bl_idname)
                for attr in dir(node):
                    if not attr.startswith("__") and hasattr(new_node, attr):
                        try:
                            setattr(new_node, attr, getattr(node, attr))
                        except:
                            pass
            for link in src_mat.node_tree.links:
                from_node = target_nodes.nodes.get(link.from_node.name)
                to_node = target_nodes.nodes.get(link.to_node.name)
                if from_node and to_node:
                    try:
                        target_nodes.links.new(from_node.outputs[link.from_socket.name],
                                               to_node.inputs[link.to_socket.name])
                    except:
                        pass
            return True

        replaced_names = set()

        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue

            for slot in obj.material_slots:
                old_mat = slot.material
                if not old_mat:
                    continue
                original_name = extract_clean_base_name(old_mat.name)

                # 기존 material을 _tmp로 이름 변경
                tmp_name_base = original_name + "_tmp"
                tmp_name = tmp_name_base
                count = 1
                while tmp_name in bpy.data.materials:
                    tmp_name = f"{tmp_name_base}_{count}"
                    count += 1
                old_mat.name = tmp_name

                # 같은 이름의 메터리얼이 이미 있으면 재사용, 없으면 복사
                if original_name in bpy.data.materials:
                    target_mat = bpy.data.materials[original_name]
                else:
                    target_mat = old_mat.copy()
                    target_mat.name = original_name
                    # bpy.data.materials.append(target_mat)

                slot.material = target_mat
                convert_to_paint_shader(target_mat)
                replaced_names.add(target_mat.name)

        # apply_json (subset만)
        apply_json_to_material_subset(replaced_names)

        self.report({'INFO'}, f"{len(replaced_names)} materials converted.")
        print(f"[✔] {len(replaced_names)}개 메터리얼이 MI_Paint 기반으로 변환 완료됨: {sorted(replaced_names)}")
        return {'FINISHED'}








def apply_json_to_material_subset(_ignored=None):
    asset_name, category, json_path, _ = load_material_json_data()
    print(f"[DEBUG] asset_name: {asset_name}, category: {category}")
    print(f"[DEBUG] json_path: {json_path}")

    if not json_path or not os.path.exists(json_path):
        print("[ERROR] JSON 경로 없음 또는 파일 없음")
        return

    # 1️⃣ 선택된 오브젝트의 메터리얼 이름 수집 (.001 제거)
    selected_mat_names = set()
    for obj in bpy.context.selected_objects:
        if obj.type == 'MESH':
            for slot in obj.material_slots:
                if slot.material:
                    base_name = slot.material.name.rsplit(".", 1)[0]
                    selected_mat_names.add(base_name)

    print(f"[DEBUG] 선택된 메터리얼들: {selected_mat_names}")
    if not selected_mat_names:
        print("[WARN] 선택된 메터리얼이 없음")
        return

    # 2️⃣ JSON 로드
    with open(json_path, 'r') as f:
        try:
            data = json.load(f)
        except Exception as e:
            print(f"[ERROR] JSON 파싱 실패: {e}")
            return

    seen_names = set()

    for mesh in data.get("meshes", []):
        for mat_info in mesh.get("materials", []):
            name = mat_info.get("name")
            if not name or name not in selected_mat_names or name in seen_names:
                continue
            seen_names.add(name)

            mat = bpy.data.materials.get(name)
            if not mat or not mat.use_nodes:
                print(f"[SKIP] {name} → 머티리얼 없음 or 노드 꺼짐")
                continue

            nodes = mat.node_tree.nodes
            links = mat.node_tree.links

            diffuse_value = mat_info.get("Diffuse")
            print(f"[DEBUG] {name} Diffuse 값: {diffuse_value}")

            # ✅ 컬러인 경우
            if isinstance(diffuse_value, list) and len(diffuse_value) >= 3:
                rgb_node = next((n for n in nodes if n.type == 'RGB' and n.name == "Diffuse Color"), None)
                if rgb_node:
                    rgb_node.outputs[0].default_value = (*diffuse_value[:3], 1.0)
                    print(f"[✔] {name} 컬러 적용됨: {diffuse_value}")
                else:
                    print(f"[WARN] {name} → 'Diffuse Color' 노드 없음")

                # Diffuse Mix = 0.0
                mix_node = next((n for n in nodes if n.name == "Diffuse Mix"), None)
                if mix_node:
                    mix_node.inputs[0].default_value = 0.0
                    print(f"[✔] {name} → 'Diffuse Mix' = 0.0 (컬러 전용)")

            # ✅ 텍스처 경로인 경우
            elif isinstance(diffuse_value, str):
                try:
                    img = bpy.data.images.load(diffuse_value, check_existing=True)
                    tex_node = next((n for n in nodes if n.type == 'TEX_IMAGE' and n.name == "Diffuse Texture"), None)
                    if tex_node:
                        tex_node.image = img
                        tex_node.image.colorspace_settings.name = 'sRGB'
                        print(f"[✔] {name} 텍스처 적용됨: {img.name}")
                    else:
                        print(f"[WARN] {name} → 'Diffuse Texture' 노드 없음")
                except Exception as e:
                    print(f"[ERROR] {name} 텍스처 로드 실패: {e}")

                # Diffuse Mix = 1.0
                mix_node = next((n for n in nodes if n.name == "Diffuse Mix"), None)
                if mix_node:
                    mix_node.inputs[0].default_value = 1.0
                    print(f"[✔] {name} → 'Diffuse Mix' = 1.0 (텍스처 사용)")

                # ✅ UV Mapping (텍스처 매핑) 적용
                textures = mat_info.get("textures", {})   # ⬅️ 추가
                uv_data = textures.get("uv")
                if uv_data:
                    mapping_node = next((n for n in nodes if n.type == 'MAPPING' and n.name == "Diffuse Mapping"), None)
                    if mapping_node:
                        repeat_u = uv_data.get("repeatU", 1.0)
                        repeat_v = uv_data.get("repeatV", 1.0)
                        offset_u = uv_data.get("offsetU", 0.0)
                        offset_v = uv_data.get("offsetV", 0.0)

                        mapping_node.inputs["Scale"].default_value = (repeat_u, repeat_v, 1.0)
                        mapping_node.inputs["Location"].default_value = (offset_u, offset_v, 0.0)
                        mapping_node.inputs["Rotation"].default_value = (0.0, 0.0, 0.0)

                        print(f"[✔] {name} → Mapping 적용됨")
                        print(f"     ↳ Scale = ({repeat_u}, {repeat_v})")
                        print(f"     ↳ Location = ({offset_u}, {offset_v})")
                    else:
                        print(f"[WARN] {name} → 'Diffuse Mapping' 노드 없음, UV 무시됨")

            else:
                print(f"[SKIP] {name} → Diffuse 값이 무효 or 없음: {diffuse_value}")



class SIMPLE_OT_import_fbx(bpy.types.Operator):
    bl_idname = "simple.import_fbx"
    bl_label = "Import and Apply Material"
    
    filepath : bpy.props.StringProperty(subtype="FILE_PATH")

    def execute(self, context):
        # FBX 파일을 가져옵니다
        bpy.ops.import_scene.fbx(filepath=self.filepath)

        # 언더스코어 "_"를 기준으로 파일 이름을 분할하여 어셋 이름을 가져옵니다
        asset_name = get_current_scene_asset_name()

        # 가져온 armature 객체를 찾습니다
        armature = None
        for obj in bpy.context.selected_objects:
            if obj.type == 'ARMATURE':
                armature = obj
                break

        if armature:
            # amature의 이름을 어셋 이름으로 설정합니다
            armature.name = asset_name + "_Armature"
                # 루트 객체 찾기
                
        root_obj = None
        for obj in bpy.context.selected_objects:
            if obj.type == 'EMPTY' and obj.parent is None:
                root_obj = obj
                break

        if root_obj:
            # 루트 객체의 스케일을 100배로 설정
            root_obj.scale = (0.01, 0.01, 0.01)
            
        # apply_matching_materials() 함수를 호출하여 메테리얼을 적용합니다
        apply_matching_materials()

        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

class SIMPLE_OT_import_usd(bpy.types.Operator):
    bl_idname = "simple.import_usd"
    bl_label = "Import USD"

    filepath: bpy.props.StringProperty(subtype="FILE_PATH")

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        # 1. USD 파일 임포트
        bpy.ops.wm.usd_import(filepath=self.filepath)
        print(f"[USD Import] {self.filepath}")

        # 2. 메터리얼 자동 매칭
        apply_matching_materials()

        # 3. '_sm_geo' 메쉬에 subdivision 적용 (전용 오퍼레이터 호출)
        bpy.ops.sf.subdivide_class1()

        # 4. 루트 EMPTY 스케일 조정
        root_obj = next(
            (obj for obj in bpy.context.selected_objects if obj.type == 'EMPTY' and obj.parent is None),
            None
        )
        if root_obj:
            root_obj.scale = (0.01, 0.01, 0.01)
            print(f"[Scale] 루트 오브젝트 스케일 적용됨: {root_obj.name}")

        self.report({'INFO'}, "USD 임포트 및 후처리 완료")
        return {'FINISHED'}


class SF_ReloadAllImages(bpy.types.Operator):
    """Reload all images in Blender"""
    bl_idname = "sf.reload_all_images"
    bl_label = "Reload All Images"

    def execute(self, context):
        for img in bpy.data.images:
            img.reload()
        self.report({'INFO'}, "All images reloaded")
        return {'FINISHED'}
        
class ReloadTextureOperator(bpy.types.Operator):
    bl_idname = "texture.reload"
    bl_label = "Reload Selected Texture"


    def execute(self, context):
        # 현재 선택한 노드 활성화
        active_node = node

        if active_node and active_node.type == 'TEX_IMAGE':
            # 텍스처 이미지 노드인 경우에만 리로드
            active_node.image.reload()

        return {'FINISHED'}

class OBJECT_OT_ApplyAllGeometryNodesSettings(bpy.types.Operator):
    bl_idname = "object.apply_all_geometry_nodes_settings"
    bl_label = "Apply All Geometry Nodes Settings"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        filepath = bpy.context.blend_data.filepath
        asset_line_name = f"{asset_name}_line"

        # 어셋 이름에 "_line"을 추가한 이름을 가진 오브젝트 찾기
        asset_line_obj = bpy.data.objects.get(asset_line_name)
        if not asset_line_obj or asset_line_obj.type != 'MESH':
            self.report({'ERROR'}, "Active object is not a mesh or no object selected.")
            return {'CANCELLED'}

        # Geometry Nodes 수정자 찾기
        geo_mod = next((mod for mod in asset_line_obj.modifiers if mod.type == 'NODES'), None)
        if not geo_mod:
            self.report({'ERROR'}, "No Geometry Nodes modifier found.")
            return {'CANCELLED'}

        # 씬의 활성 카메라 설정
        if bpy.context.scene.camera:
            geo_mod["Input_5"] = bpy.context.scene.camera
        else:
            self.report({'WARNING'}, "No active scene camera found.")

        # 레졸루션 설정
        geo_mod["Input_4"] = bpy.context.scene.render.resolution_x
        geo_mod["Input_3"] = bpy.context.scene.render.resolution_y

        # FOV 설정
        if bpy.context.scene.camera and bpy.context.scene.camera.data.type == 'PERSP':
            fov_in_radians = bpy.context.scene.camera.data.angle
            fov_in_degrees = math.degrees(fov_in_radians) + 10  # 10도를 더함
            geo_mod["Input_48"] = fov_in_degrees

        self.report({'INFO'}, "All Geometry Nodes settings applied successfully.")
        return {'FINISHED'}
 
    
    
class SF_OT_LinkRimToNode(bpy.types.Operator):
    bl_idname = "object.link_rim_to_node"
    bl_label = "Link Rim to Node"

    def execute(self, context):
        category = context.scene.my_asset_tool.category
        # character_names = ["man1F", "man2F", "women3F", "man4F", "man5F", "man6F", "women0F"]
        character_names = [name[0] for name in get_assets(category)]
        for asset_name in character_names:
            light_obj_name = f"{asset_name}_light"
            light_obj = bpy.data.objects.get(light_obj_name)

            if not light_obj:
                self.report({'WARNING'}, f"{light_obj_name} object not found, skipping...")
                continue

            for child in light_obj.children:
                if "rim01" in child.name or "rim02" in child.name:
                    rim_object = child  # Found the rim object under the specific light empty

                    # Make sure the object is linked and has a library (for linked objects)
                    if rim_object.users > 0 and (rim_object.library is None or rim_object.library is not None):
                        # Now we proceed to link this rim object to the materials
                        for material in bpy.data.materials:
                            if material.use_nodes:
                                nodes = material.node_tree.nodes
                                links = material.node_tree.links

                                for node in nodes:
                                    if node.type == 'GROUP' and node.node_tree and node.node_tree.name.startswith('SF_Toon_Logic'):
                                        input_index = 53 if "rim01" in rim_object.name else 54
                                        if 0 <= input_index < len(node.inputs):
                                            input_socket = node.inputs[input_index]
                                            existing_links = list(input_socket.links)
                                            for link in existing_links:
                                                links.remove(link)

                                            tc_node = nodes.new(type='ShaderNodeTexCoord')
                                            tc_node.object = rim_object
                                            links.new(tc_node.outputs['Object'], input_socket)

                        # Clean up unused nodes is handled here
                        self.remove_unused_nodes_from_materials()

        return {'FINISHED'}
        
    def remove_unused_nodes_from_materials(self):
        for material in bpy.data.materials:
            if material.use_nodes:
                nodes = material.node_tree.nodes
                links = material.node_tree.links

                # Collect all 'Texture Coordinate' nodes that are not connected to any other nodes
                unused_tex_coord_nodes = [
                    node for node in nodes
                    if node.type == 'TEX_COORD' and not any(link.from_node == node or link.to_node == node for link in links)
                ]

                # Delete all unused 'Texture Coordinate' nodes
                for node in unused_tex_coord_nodes:
                    # print(f"Removing unused 'Texture Coordinate' node: {node.name} from material: {material.name}")
                    nodes.remove(node)
                   
                    
class SF_OT_AddPropertiesAndLink(bpy.types.Operator):
    bl_idname = "object.sf_add_properties_and_link"
    bl_label = "Add Properties and Link to Material"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        assets, category = get_assets()
        character_names = [name[0] for name in assets]
        success_count = 0
        linethickness_prop = "P30_Line_Thickness"
        properties_info = self.get_properties_info()
        if not properties_info:
            self.report({'ERROR'}, "Failed to load properties info.")
            return {'CANCELLED'}

        for asset_name in character_names:
            collection_name = f"{asset_name}_col"
            light_obj_name = f"{asset_name}_light"
            light_obj = bpy.data.objects.get(light_obj_name)

            if not light_obj:
                self.report({'WARNING'}, f"{light_obj_name} object not found, skipping...")
                continue

            self.remove_existing_drivers(collection_name)
            self.remove_existing_properties(light_obj)
            self.add_custom_properties(light_obj, properties_info)
            self.add_drivers_to_materials(collection_name, light_obj, properties_info)

            # 불필요한 텍스처 좌표 노드 제거
            for mat in bpy.data.materials:
                self.remove_unlinked_tex_coord_nodes(mat)

            success_count += 1

        if success_count == 0:
            self.report({'ERROR'}, "No valid characters found to process")
            return {'CANCELLED'}

        bpy.ops.object.sf_link_character_lights()
        bpy.ops.scene.refresh_drivers()
        self.report({'INFO'}, f"Processed {success_count} characters successfully.")
        return {'FINISHED'}

    def find_top_level_empty(self, asset_name):
        for obj in bpy.data.objects:
            if obj.type == 'EMPTY' and obj.parent is None and asset_name in obj.name:
                return obj
        return None


    def get_properties_info(self):
        file_path = resolve_drive_path("RND/SFtools/2025/lookdev/get_properties_info.json")

        try:
            with open(file_path, 'r') as infile:
                return json.load(infile)
        except Exception as e:
            print(f"Error loading properties info from {file_path}: {e}")
            return []

    def remove_existing_drivers(self, collection_name):
        collection = bpy.data.collections.get(collection_name)
        if not collection:
            print(f"Collection '{collection_name}' not found")
            return

        for obj in collection.objects:
            if obj.type == 'MESH' and obj.data.materials:
                for mat in obj.data.materials:
                    if mat.use_nodes and mat.node_tree and mat.node_tree.animation_data:
                        drivers_to_remove = []
                        for driver in mat.node_tree.animation_data.drivers:
                            drivers_to_remove.append(driver.data_path)  # Collecting drivers before removal

                        for driver_path in drivers_to_remove:
                            try:
                                mat.node_tree.driver_remove(driver_path)
                                print(f"Successfully removed driver at {driver_path}")
                            except Exception as e:
                                print(f"Failed to remove driver at {driver_path}: {e}")

    def remove_existing_properties(self, obj):
        for prop_name in list(obj.keys()):
            del obj[prop_name]

    def add_custom_properties(self, obj, properties_info):
        obj.id_properties_ensure()  # Ensure the property manager is updated
        for prop_info in properties_info:
            prop_name = prop_info['name']
            default = prop_info['default']
            prop_type = prop_info['type']
            min_val = prop_info.get('min', 0)  # Default values for min, max if not provided
            max_val = prop_info.get('max', 1)
            soft_min = prop_info.get('soft_min', min_val)  # Use min_val if soft_min is not provided
            soft_max = prop_info.get('soft_max', max_val)  # Use max_val if soft_max is not provided

            # Set default value and type directly on the object
            obj[prop_name] = default

            # Update the property manager settings
            property_manager = obj.id_properties_ui(prop_name)
            if prop_type == "COLOR":
                property_manager.update(min=min_val, max=max_val, soft_min=soft_min, soft_max=soft_max, subtype='COLOR')
            elif prop_type == "FLOAT":
                property_manager.update(min=min_val, max=max_val, soft_min=soft_min, soft_max=soft_max, subtype='NONE')

            # After updating property_manager, ensure the default value is set correctly, especially for COLOR type
            obj[prop_name] = default
            
    def add_drivers_to_materials(self, collection_name, light_obj, properties_info):
        collection = bpy.data.collections.get(collection_name)
        if not collection:
            print(f"[ERROR] Collection '{collection_name}' not found.")
            return

        for obj in collection.objects:
            if obj.type == 'MESH' and obj.data.materials:
                for mat in obj.data.materials:
                    if mat.use_nodes:
                        for node in mat.node_tree.nodes:
                            if node.type == 'GROUP' and node.node_tree and node.node_tree.name == "SF_Toon_v03":
                                for prop_info in properties_info:
                                    prop_name = prop_info['name']
                                    default = prop_info['default']
                                    prop_type = prop_info['type']
                                    input_idx = prop_info['index']

                                    # ✅ 라인 두께는 Line Size (Overall) 인풋에만 연결
                                    if prop_name == "P30_Line_Thickness":
                                        for idx, inp in enumerate(node.inputs):
                                            if inp.name == "Line Size(Overall)":
                                                self.add_driver_to_material(
                                                    mat, node, prop_name, 0.1, "VALUE", idx, light_obj
                                                )
                                    else:
                                        self.add_driver_to_material(
                                            mat, node, prop_name, default, prop_type, input_idx, light_obj
                                        )


    def add_driver_to_material(self, mat, node, prop_name, default, prop_type, input_idx, light_obj):
        try:
            if input_idx >= len(node.inputs):
                print(f"[SKIP] 노드 인덱스 {input_idx}가 유효하지 않습니다.")
                return

            node_input = node.inputs[input_idx]
            path_base = f'nodes["{node.name}"].inputs[{input_idx}].default_value'

            # 속성 존재하지 않으면 기본값 설정
            if prop_name not in light_obj:
                if prop_type == "COLOR":
                    light_obj[prop_name] = [1.0, 1.0, 1.0, 1.0]
                elif prop_type == "VALUE":
                    light_obj[prop_name] = default

            # COLOR 타입: RGBA 채널 모두에 드라이버 추가
            if prop_type == "COLOR":
                for i in range(4):  # R,G,B,A
                    fcurve = mat.node_tree.driver_add(path_base, i)
                    driver = fcurve.driver
                    driver.type = 'AVERAGE'
                    while driver.variables:
                        driver.variables.remove(driver.variables[0])
                    var = driver.variables.new()
                    var.name = "var"
                    var.type = 'SINGLE_PROP'
                    var.targets[0].id_type = 'OBJECT'
                    var.targets[0].id = light_obj
                    var.targets[0].data_path = f'["{prop_name}"][{i}]'

            # VALUE 타입: 단일 값
            elif prop_type == "VALUE":
                fcurve = mat.node_tree.driver_add(path_base)
                driver = fcurve.driver
                driver.type = 'AVERAGE'
                while driver.variables:
                    driver.variables.remove(driver.variables[0])
                var = driver.variables.new()
                var.name = "var"
                var.type = 'SINGLE_PROP'
                var.targets[0].id_type = 'OBJECT'
                var.targets[0].id = light_obj
                var.targets[0].data_path = f'["{prop_name}"]'

            # 강제 갱신
            bpy.context.view_layer.update()
            bpy.context.evaluated_depsgraph_get().update()
            print(f"[✔] 드라이버 연결됨: {mat.name} → {node.name} input[{input_idx}]")

        except Exception as e:
            print(f"[ERROR] 드라이버 연결 실패: {e}")




    def setup_driver(self, fcurves, obj, prop_name, idx=None):
        for fcurve in fcurves:
            driver = fcurve.driver
            driver.type = 'AVERAGE'
            driver.variables.clear()

            var = driver.variables.new()
            var.name = 'var'
            var.type = 'SINGLE_PROP'

            target = var.targets[0]
            target.id_type = 'OBJECT'

            # ✅ 반드시 직접 참조로
            target.id = bpy.data.objects.get(obj.name)

            if not target.id:
                print(f"[ERROR] 드라이버 타겟 오브젝트를 찾을 수 없음: {obj.name}")
                continue

            # ✅ 정확한 data_path 설정
            if idx is not None:
                target.data_path = f'["{prop_name}"][{idx}]'
            else:
                target.data_path = f'["{prop_name}"]'

            print(f"[DRIVER OK] {target.id.name} → {target.data_path}")




    def add_driver_to_modifier_thickness(self, target_obj, modifier_name, driver_source, linethickness_prop):
        # 드라이버를 추가할 솔리디파이 모디파이어의 thickness 속성을 찾습니다.
        modifier = target_obj.modifiers.get(modifier_name)
        if modifier and modifier.type == 'SOLIDIFY':
            # 드라이버가 이미 존재하는지 확인하고, 있다면 제거합니다.
            if target_obj.animation_data and target_obj.animation_data.drivers:
                # 모든 드라이버를 순회합니다.
                for fcurve in target_obj.animation_data.drivers:
                    # 해당 모디파이어의 thickness 속성에 대한 드라이버를 찾습니다.
                    if fcurve.data_path == f'modifiers["{modifier_name}"].thickness':
                        # 해당 드라이버를 제거합니다.
                        target_obj.driver_remove(fcurve.data_path)

            # 드라이버 설정
            fcurve = target_obj.driver_add(f'modifiers["{modifier_name}"].thickness')
            driver = fcurve.driver
            driver.type = 'AVERAGE'

            var = driver.variables.new()
            var.name = 'var'
            var.targets[0].id = driver_source
            var.targets[0].data_path = f'["{linethickness_prop}"]'
        else:
            self.report({'WARNING'}, "Modifier not found or not a Solidify modifier.")


    def process_all_meshes(self, parent_obj, driver_source, linethickness_prop):
        if not parent_obj:
            print("[ERROR] parent_obj is None. Skipping.")
            return

        for obj in parent_obj.children:
            if obj.type == 'MESH':
                for modifier in obj.modifiers:
                    if modifier.type == 'SOLIDIFY':
                        self.add_driver_to_modifier_thickness(obj, modifier.name, driver_source, linethickness_prop)

            # 재귀 호출 전에도 obj가 비어 있지 않은지 체크
            self.process_all_meshes(obj, driver_source, linethickness_prop)

            
    def find_active_rim_object(self, asset_name):
        # Find the parent Empty object
        parent_name = f"{asset_name}_light"
        parent_obj = bpy.data.objects.get(parent_name)
        if not parent_obj:
            print(f"Parent object '{parent_name}' not found.")
            return None

        # Check for active object among the children
        for child in parent_obj.children:
            if child.name.startswith(f"{asset_name}_rim") and child.select_get():
                return child

        print("No active rim object found under the specified parent.")
        return None

    def link_rim_to_node(self, context, asset_name):
        print(f"시작: {asset_name}에 대한 림 오브젝트를 찾는 중...")
        
        # 활성 림 오브젝트 검색
        active_rim_obj = self.find_active_rim_object(asset_name)
        if not active_rim_obj:
            print("실패: 활성 림 오브젝트를 찾을 수 없습니다.")
            return
        else:
            print(f"성공: 활성 림 오브젝트 '{active_rim_obj.name}'를 찾았습니다.")
        
        # 재료 컬렉션 검색
        material_collection_name = f"{asset_name}_col"
        print(f"재료 컬렉션 '{material_collection_name}'를 검색 중...")
        material_collection = bpy.data.collections.get(material_collection_name)
        if not material_collection:
            print(f"실패: 재료 컬렉션 '{material_collection_name}'을 찾을 수 없습니다.")
            return
        else:
            print(f"성공: 재료 컬렉션 '{material_collection_name}'을 찾았습니다.")
        
        # 림 오브젝트와 재료 컬렉션 연결
        if active_rim_obj.type == 'MESH' and active_rim_obj.data.materials:
            for mat in active_rim_obj.data.materials:
                if mat.use_nodes:
                    nodes = mat.node_tree.nodes
                    links = mat.node_tree.links
                    print(f"노드 수정 중: 재료 '{mat.name}'...")
                    for node in nodes:
                        if node.type == 'GROUP' and node.node_tree and node.node_tree.name.startswith('SF_Toon_Logic'):
                            rim_name = active_rim_obj.name[len(asset_name)+1:]
                            input_index = 53 if "rim01" in rim_name else 54
                            
                            if 0 <= input_index < len(node.inputs):
                                input_socket = node.inputs[input_index]
                                # 기존 링크 제거
                                existing_links = list(input_socket.links)
                                for link in existing_links:
                                    links.remove(link)
                                
                                # 새 텍스처 좌표 노드 생성 및 링크
                                tc_node = nodes.new(type='ShaderNodeTexCoord')
                                tc_node.object = active_rim_obj
                                links.new(tc_node.outputs['Object'], input_socket)
                                print(f"성공: '{rim_name}'에 대한 노드 연결 완료.")
                            else:
                                print(f"실패: 입력 인덱스 '{input_index}'가 범위를 벗어났습니다.")
                else:
                    print(f"노드 사용 안함: 재료 '{mat.name}'는 노드를 사용하지 않습니다.")
        else:
            print(f"오류: '{active_rim_obj.name}' 오브젝트는 메쉬 타입이 아니거나 재료가 없습니다.")



    def remove_unlinked_tex_coord_nodes(self, material):
        if material.node_tree:
            for node in material.node_tree.nodes:
                # 'Texture Coordinate' 노드이고, 어떤 출력도 연결되지 않은 경우
                if node.type == 'TEX_COORD' and not any(output.is_linked for output in node.outputs):
                    # 노드 삭제
                    material.node_tree.nodes.remove(node)

# ======================================================
# 유틸: 렌더 세팅 저장 / 복원
# ======================================================
def save_render_settings(scene):
    settings = {
        "engine": scene.render.engine,
        "samples": getattr(scene.cycles, "samples", None),
        "denoise": getattr(scene.cycles, "use_denoising", None),
    }
    scene["sf_prev_render_settings"] = settings
    print("[INFO] 이전 렌더 설정 저장:", settings)


def restore_render_settings(scene):
    settings = scene.get("sf_prev_render_settings", None)
    if not settings:
        print("[WARN] 복원할 설정 없음")
        return

    scene.render.engine = settings.get("engine", "BLENDER_EEVEE")
    if scene.render.engine == 'CYCLES':
        if settings.get("samples"): 
            scene.cycles.samples = settings["samples"]
        if settings.get("denoise") is not None:
            scene.cycles.use_denoising = settings["denoise"]

    print("[INFO] 이전 렌더 설정 복원:", settings)

class SF_OT_LineDefaultSettings(bpy.types.Operator):
    bl_idname = "sf.line_default_settings"
    bl_label = "Line Default Settings"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # 기본 실행은 아무것도 안함 (팝업 안에서 버튼 눌러야 적용됨)
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.label(text="적용 대상을 선택하세요:")
        row = layout.row(align=True)
        row.operator("sf.line_default_settings_apply", text="All", icon="MATERIAL").target = 'ALL'
        row.operator("sf.line_default_settings_apply", text="Selected", icon="RESTRICT_SELECT_OFF").target = 'SELECTED'


class SF_OT_LineDefaultSettingsApply(bpy.types.Operator):
    bl_idname = "sf.line_default_settings_apply"
    bl_label = "Apply Line Default Settings"

    target: bpy.props.StringProperty(default="ALL")

    def execute(self, context):
        mats_to_check = []

        if self.target == 'ALL':
            mats_to_check = bpy.data.materials
        else:  # SELECTED
            for obj in context.selected_objects:
                if obj.type == 'MESH':
                    for slot in obj.material_slots:
                        if slot.material:
                            mats_to_check.append(slot.material)

        mats_to_check = list(set(mats_to_check))  # 중복 제거
        applied = 0

        for mat in mats_to_check:
            if not mat.use_nodes or not mat.node_tree:
                continue
            node = mat.node_tree.nodes.get("Group.004")
            if not node:
                continue
            try:

                node.inputs[30].default_value = 0.5
                node.inputs[31].default_value = 1
                node.inputs[32].default_value = 0.2
                node.inputs[33].default_value = 0.1
                node.inputs[35].default_value = 1
                node.inputs[47].default_value = 0.5
                applied += 1
                print(f"[OK] {mat.name}: Group.004 기본값 적용")
            except Exception as e:
                print(f"[WARN] {mat.name}: 적용 실패 ({e})")

        self.report({'INFO'}, f"{applied}개 머티리얼 기본값 적용 완료 ({self.target})")
        return {'FINISHED'}

import bpy
import os

def get_or_link_nodegroup(node_group_name, ref_name="SF_Toon_v03"):
    """ref_name이 이미 링크된 경우 같은 라이브러리에서 node_group_name을 불러온다"""
    ng = bpy.data.node_groups.get(node_group_name)
    if ng:
        return ng

    ref_ng = bpy.data.node_groups.get(ref_name)
    if not ref_ng or not ref_ng.library:
        print(f"[ERROR] '{ref_name}' 의 라이브러리 정보를 찾을 수 없음")
        return None

    libpath = bpy.path.abspath(ref_ng.library.filepath)

    with bpy.data.libraries.load(libpath, link=True) as (data_from, data_to):
        if node_group_name in data_from.node_groups:
            data_to.node_groups = [node_group_name]
            print(f"[OK] '{node_group_name}' 노드 그룹을 {libpath} 에서 링크 불러옴")
        else:
            print(f"[ERROR] '{node_group_name}' 노드 그룹을 {libpath} 에서 찾을 수 없음")
            return None

    return bpy.data.node_groups.get(node_group_name)


class SF_OT_ColorMode(bpy.types.Operator):
    bl_idname = "sf.color_mode"
    bl_label = "Switch to Color Mode"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        sc = context.scene

        # --- Eevee 세팅 ---
        sc.render.engine = 'BLENDER_EEVEE'
        sc.eevee.use_soft_shadows = True
        sc.eevee.use_gtao = True
        sc.eevee.taa_render_samples = 64
        sc.eevee.taa_samples = 16
        print("[INFO] Eevee 세팅 완료")

        # --- 머티리얼 복원 (SF_Toon_cycle → SF_Toon_v03) ---
        restored = 0
        ng_toon_v03 = bpy.data.node_groups.get("SF_Toon_v03")
        if not ng_toon_v03:
            self.report({'ERROR'}, "SF_Toon_v03 노드 그룹이 없음")
            return {'CANCELLED'}

        for mat in bpy.data.materials:
            if mat.use_nodes and mat.node_tree:
                for node in mat.node_tree.nodes:
                    if node.type == 'GROUP' and node.node_tree:
                        if node.node_tree.name == "SF_Toon_cycle":
                            node.node_tree = ng_toon_v03
                            restored += 1
                            print(f"[OK] {mat.name}: {node.name} → SF_Toon_v03 복원")

        self.report({'INFO'}, f"{restored}개 머티리얼 복원 완료 (Color Mode)")
        return {'FINISHED'}


class SF_OT_LineMode(bpy.types.Operator):
    bl_idname = "sf.line_mode"
    bl_label = "Switch to Line Mode"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        sc = context.scene

        # --- Cycles 세팅 ---
        sc.render.engine = 'CYCLES'
        sc.cycles.device = 'CPU'
        sc.cycles.shading_system = True   # ✅ OSL 켜기
        sc.cycles.use_adaptive_sampling = True
        sc.cycles.adaptive_threshold = 0.1
        sc.cycles.samples = 8
        sc.cycles.use_denoising = True
        print("[INFO] Cycles + OSL 세팅 완료")

        # --- 머티리얼 교체 (SF_Toon_v03 → SF_Toon_cycle) ---
        ng_toon_cycle = get_or_link_nodegroup("SF_Toon_cycle", ref_name="SF_Toon_v03")
        if not ng_toon_cycle:
            self.report({'ERROR'}, "SF_Toon_cycle 노드 그룹을 불러올 수 없음")
            return {'CANCELLED'}

        switched = 0
        for mat in bpy.data.materials:
            if mat.use_nodes and mat.node_tree:
                for node in mat.node_tree.nodes:
                    if node.type == 'GROUP' and node.node_tree:
                        if node.node_tree.name == "SF_Toon_v03":
                            node.node_tree = ng_toon_cycle
                            switched += 1
                            print(f"[OK] {mat.name}: {node.name} → SF_Toon_cycle 교체")

        self.report({'INFO'}, f"{switched}개 머티리얼 전환 완료 (Line Mode)")
        return {'FINISHED'}

        
# ======================================================
# EnumProperty (스위처)
# ======================================================
def update_render_mode(self, context):
    if context.scene.sf_render_mode == 'LINE':
        bpy.ops.sf.line_mode()
    else:
        bpy.ops.sf.color_mode()


def register_props():
    bpy.types.Scene.sf_render_mode = bpy.props.EnumProperty(
        name="Render Mode",
        items=[
            ('COLOR', "Color Mode", "Eevee Lookdev"),
            ('LINE', "Line Mode", "Cycles + SF_Toon_cycle"),
        ],
        default='COLOR',
        update=update_render_mode
    )



        
class SF_OT_LoadAndLinkNodeGroupC(bpy.types.Operator):
    bl_idname = "object.sf_load_and_link_nodegroupc"
    bl_label = "Load and Link SF_Toon_cycle + EasyToon (Cycles)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        import os

        # --- 1. Cycles 세팅 강제 적용 (제일 먼저!) ---
        sc = context.scene
        sc.render.engine = 'CYCLES'
        sc.cycles.device = 'CPU'
        sc.cycles.shading_system = True       # OSL 켜기
        sc.cycles.use_adaptive_sampling = True
        sc.cycles.adaptive_threshold = 0.1    # Noise Threshold
        sc.cycles.samples = 8                 # Max Samples
        sc.cycles.use_denoising = True
        print("[INFO] Cycles + OSL 세팅 완료")

        # --- 2. SF_Toon_cycle 노드 그룹 링크 ---
        node_group_name = "SF_Toon_cycle"
        library_filepath = resolve_script_path("blend", "ldvLight_cycle.blend")

        def normalize_path(path):
            return os.path.normpath(path).replace("\\", "/").lower()

        with bpy.data.libraries.load(library_filepath, link=True) as (data_from, data_to):
            if node_group_name in data_from.node_groups:
                data_to.node_groups = [node_group_name]
            else:
                self.report({'ERROR'}, f"'{library_filepath}'에서 '{node_group_name}' 찾을 수 없습니다.")
                return {'CANCELLED'}

        linked_group = None
        for node_group in bpy.data.node_groups:
            if (
                node_group.library
                and normalize_path(node_group.library.filepath) == normalize_path(library_filepath)
                and node_group.name == node_group_name
            ):
                linked_group = node_group
                break

        if not linked_group:
            self.report({'ERROR'}, f"링크된 노드 그룹 '{node_group_name}' 찾을 수 없습니다.")
            return {'CANCELLED'}

        # --- 3. EasyToon OSL 경로 ---
        EASYTOON_OSL_PATH = r"M:\RND\SFtools\2025\lookdev\blend\CNPRK_EasyToon.osl"
        if not os.path.exists(EASYTOON_OSL_PATH):
            self.report({'ERROR'}, f"EasyToon OSL 파일 없음: {EASYTOON_OSL_PATH}")
            return {'CANCELLED'}

        # --- 4. 모든 머티리얼 순회 (SF_Toon → SF_Toon_cycle 교체 + EasyToon 연결) ---
        updated = 0
        for mat in bpy.data.materials:
            if mat.use_nodes and mat.node_tree:
                nodes = mat.node_tree.nodes
                links = mat.node_tree.links

                for node in nodes:
                    if node.type == 'GROUP' and node.node_tree:
                        if node.node_tree.name.startswith("SF_Toon"):
                            # SF_Toon → SF_Toon_cycle 교체
                            node.node_tree = linked_group
                            updated += 1

                            # 기존 EasyToon Script 제거
                            for n in [n for n in nodes if n.type == 'SCRIPT' and n.label == "EasyToon"]:
                                nodes.remove(n)

                            # 새 EasyToon Script 노드 생성
                            easy_node = nodes.new("ShaderNodeScript")
                            easy_node.label = "EasyToon"
                            easy_node.name = "EasyToon"
                            easy_node.mode = 'EXTERNAL'
                            easy_node.filepath = EASYTOON_OSL_PATH
                            try:
                                easy_node.update()
                            except:
                                self.report({'WARNING'}, f"{mat.name}: EasyToon 업데이트 실패")

                            easy_node.location = (node.location.x - 300, node.location.y)

                            # 출력 → SF_Toon_cycle 입력 연결
                            socket_map = [
                                ("Shading", "Shading"),
                                ("LineArt", "LineArt"),
                                ("OutputShadow", "OutputShadow"),
                            ]

                            for out_name, in_name in socket_map:
                                # EasyToon 쪽 출력 찾기 (대소문자 무시)
                                out_socket = next((o for o in easy_node.outputs if o.name.lower() == out_name.lower()), None)
                                # SF_Toon_cycle 쪽 입력 찾기 (대소문자 무시)
                                in_socket = next((i for i in node.inputs if i.name.lower() == in_name.lower()), None)

                                if out_socket and in_socket:
                                    links.new(out_socket, in_socket)
                                    print(f"[OK] 연결됨: {easy_node.label}.{out_socket.name} → {node.name}.{in_socket.name}")
                                else:
                                    print(f"[WARN] 소켓을 찾을 수 없음: {out_name} → {in_name}")

        if updated > 0:
            self.report({'INFO'}, f"{updated}개 머티리얼에 '{node_group_name}' + EasyToon 적용 완료.")
        else:
            self.report({'WARNING'}, f"'{node_group_name}' 사용한 머티리얼을 찾지 못했습니다.")

        # --- 5. Outline 전체 삭제 (ALL 모드 강제) ---
        try:
            context.scene.outline_target_mode = 'ALL'
            bpy.ops.object.sf_remove_outline()
            self.report({'INFO'}, "모든 Outline 삭제 완료 (ALL 모드)")
        except Exception as e:
            self.report({'WARNING'}, f"Outline 삭제 실패 (무시됨): {e}")

        # --- 6. EasyToon 프리셋 적용 ---
        try:
            bpy.context.scene.NPRSettings.scene_preset = 'DRAFT'
            self.report({'INFO'}, "EasyToon 프리셋 DRAFT 적용 완료")
        except Exception as e:
            self.report({'WARNING'}, f"EasyToon 프리셋 적용 실패 (무시됨): {e}")
        # --- 7. 라이트 처리: *_light_spec 삭제 ---
        try:
            deleted = 0
            for obj in list(bpy.data.objects):
                if obj.name.endswith("_light_spec"):
                    bpy.data.objects.remove(obj, do_unlink=True)
                    deleted += 1
            self.report({'INFO'}, f"{deleted}개의 *_light_spec 오브젝트 삭제 완료")
        except Exception as e:
            self.report({'WARNING'}, f"라이트 삭제 실패: {e}")

        return {'FINISHED'}




class SF_OT_LoadAndLinkNodeGroup(bpy.types.Operator):
    bl_idname = "object.sf_load_and_link_nodegroup"
    bl_label = "Load and Link SF_Toon_Logic Node Group"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        node_group_name = "SF_Toon_v03"
        library_filepath = resolve_script_path("blend", "ldvLight_v03.blend")
        def normalize_path(path):
            return os.path.normpath(path).replace("\\", "/").lower()
        # print(f"[DEBUG] 노드 그룹 로딩 시작: {node_group_name} from {library_filepath}")

        # 노드 그룹 링크 시도
        with bpy.data.libraries.load(library_filepath, link=True) as (data_from, data_to):
            # print(f"[DEBUG] 라이브러리 안 노드 그룹들: {data_from.node_groups}")
            if node_group_name in data_from.node_groups:
                data_to.node_groups = [node_group_name]
                # print(f"[DEBUG] '{node_group_name}' 노드 그룹을 링크합니다.")
            else:
                self.report({'ERROR'}, f"'{library_filepath}'에서 '{node_group_name}' 찾을 수 없습니다.")
                return {'CANCELLED'}

        # 링크된 노드 그룹 검색
        linked_group = None
        for node_group in bpy.data.node_groups:
            if (
                node_group.library and
                normalize_path(node_group.library.filepath) == normalize_path(library_filepath) and
                node_group.name == node_group_name
            ):
                linked_group = node_group
                # print(f"[DEBUG] 링크된 노드 그룹 확인됨: {linked_group.name}")
                break

        if not linked_group:
            self.report({'ERROR'}, f"링크된 노드 그룹 '{node_group_name}' 찾을 수 없습니다.")
            return {'CANCELLED'}

        # 모든 메터리얼에서 해당 노드 그룹 교체
        updated = 0
        for mat in bpy.data.materials:
            if mat.use_nodes and mat.node_tree:
                for node in mat.node_tree.nodes:
                    if node.type == 'GROUP' and node.node_tree:
                        if node.node_tree.name.startswith("SF_Toon"):
                            # print(f"[DEBUG] 머티리얼 '{mat.name}'의 노드 '{node.name}' 교체됨")
                            node.node_tree = linked_group
                            updated += 1

        if updated > 0:
            self.report({'INFO'}, f"{updated}개 머티리얼에 '{node_group_name}' 적용 완료.")
        else:
            self.report({'WARNING'}, f"'{node_group_name}' 사용한 머티리얼을 찾지 못했습니다.")

        # bpy.ops.object.sf_create_character_lights()
        # bpy.ops.object.sf_add_properties_and_link()

        return {'FINISHED'}

        
class SF_OT_LinkCharacterLights(bpy.types.Operator):
    bl_idname = "object.sf_link_character_lights"
    bl_label = "Link Character Lights"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        import bpy
        major, minor = bpy.app.version[:2]
        is_eevee_next = (major, minor) >= (4, 2)

        assets, category = get_assets()
        if not assets:
            self.report({'ERROR'}, "어셋 이름을 추출할 수 없습니다.")
            return {'CANCELLED'}

        asset_name = assets[0][0]
        target_light_group = f"{asset_name}_lgt"
        target_collection_name = f"{asset_name}_light_col"

        # --- EEVEE Next인 경우 생략 ---
        if is_eevee_next:
            self.report({'INFO'}, "EEVEE Next에서는 light_groups 기능이 비활성화되어 생략됩니다.")
            print("[INFO] Skipping light_groups assignment (EEVEE Next detected)")
            return {'FINISHED'}

        # --- 1️⃣ 라이트 컬렉션에 라이트 그룹 지정 ---
        target_collection = bpy.data.collections.get(target_collection_name)
        if target_collection:
            for obj in target_collection.objects:
                if obj.type == 'LIGHT':
                    light_data = obj.data
                    if not hasattr(light_data, "light_groups"):
                        print(f"[WARN] '{obj.name}'은 light_groups 속성이 없음 (EEVEE Next 또는 Cycles 전용)")
                        continue

                    light_data.light_groups.use_default = False
                    light_data.light_groups.groups.clear()
                    new_group = light_data.light_groups.groups.add()
                    new_group.name = target_light_group
                    print(f"[LIGHT] '{obj.name}' → 그룹: {target_light_group}")
                else:
                    print(f"[SKIP] '{obj.name}'는 라이트가 아님")
        else:
            self.report({'WARNING'}, f"컬렉션 '{target_collection_name}'을 찾을 수 없습니다.")

        # --- 2️⃣ 씬의 모든 머티리얼에 동일한 라이트 그룹 설정 ---
        print(f"[INFO] 모든 머티리얼에 라이트 그룹 '{target_light_group}' 적용 중...")
        for mat in bpy.data.materials:
            if not mat.use_nodes:
                continue
            if not hasattr(mat, "light_groups"):
                print(f"[WARN] 머티리얼 '{mat.name}'은 light_groups 속성이 없음 (Cycles 비활성?)")
                continue

            mat.light_groups.use_default = False
            mat.light_groups.groups.clear()
            new_group = mat.light_groups.groups.add()
            new_group.name = target_light_group
            print(f"[MATERIAL] '{mat.name}' → 그룹: {target_light_group}")

        self.report({'INFO'}, f"라이트 및 머티리얼에 '{target_light_group}' 그룹 적용 완료")
        return {'FINISHED'}



        
class SF_OT_LinkRimToNode(bpy.types.Operator):
    bl_idname = "object.link_rim_to_node"
    bl_label = "Link Rim to Node"

    def execute(self, context):
        # character_names = ["man1F", "man2F", "women3F", "man4F", "man5F", "man6F", "women0F"]
        category = context.scene.my_asset_tool.category
        # character_names = ["man1F", "man2F", "women3F", "man4F", "man5F", "man6F", "women0F", "cockroach"]
        character_names = [name[0] for name in get_assets(category)]
        for asset_name in character_names:
            # Finding the rim objects in the corresponding light collection
            light_col = bpy.data.collections.get(f"{asset_name}_light_col")
            if not light_col:
                self.report({'WARNING'}, f"{asset_name}_light_col collection not found, skipping...")
                continue

            rim_objects = [obj for obj in light_col.objects if "rim01" in obj.name or "rim02" in obj.name]
            if not rim_objects:
                self.report({'WARNING'}, f"No rim objects found in {asset_name}_light_col, skipping...")
                continue

            # Finding the materials in the asset collection
            asset_col = bpy.data.collections.get(f"{asset_name}_col")
            if not asset_col:
                self.report({'WARNING'}, f"{asset_name}_col collection not found, skipping...")
                continue

            # Process each object in the asset collection to update materials
            for obj in asset_col.all_objects:
                if obj.type == 'MESH' and obj.material_slots:
                    for slot in obj.material_slots:
                        if slot.material and slot.material.use_nodes:
                            nodes = slot.material.node_tree.nodes
                            links = slot.material.node_tree.links
                            # Linking rim objects to the materials
                            for rim_object in rim_objects:
                                for node in nodes:
                                    if node.type == 'GROUP' and node.node_tree and node.node_tree.name.startswith('SF_Toon_Logic'):
                                        input_index = 53 if "rim01" in rim_object.name else 54
                                        if 0 <= input_index < len(node.inputs):
                                            input_socket = node.inputs[input_index]
                                            # Remove existing links to the input socket
                                            existing_links = list(input_socket.links)
                                            for link in existing_links:
                                                links.remove(link)
                                            # Create a new Texture Coordinate node and link it
                                            tc_node = nodes.new(type='ShaderNodeTexCoord')
                                            tc_node.object = rim_object
                                            links.new(tc_node.outputs['Object'], input_socket)
                        if node.type == 'TEX_COORD' and not any(output.is_linked for output in node.outputs):
                            material.node_tree.nodes.remove(node)
            # Optional: Implement this function to clean up unused nodes
            self.remove_unused_nodes_from_materials()

        return {'FINISHED'}
        
    def remove_unused_nodes_from_materials(self):
        for material in bpy.data.materials:
            if material.use_nodes:
                nodes = material.node_tree.nodes
                links = material.node_tree.links

                # Collect all 'Texture Coordinate' nodes that are not connected to any other nodes
                unused_tex_coord_nodes = [
                    node for node in nodes
                    if node.type == 'TEX_COORD' and not any(link.from_node == node or link.to_node == node for link in links)
                ]

                # Delete all unused 'Texture Coordinate' nodes
                for node in unused_tex_coord_nodes:
                    # print(f"Removing unused 'Texture Coordinate' node: {node.name} from material: {material.name}")
                    nodes.remove(node)

class SubdivideClass1(bpy.types.Operator):
    bl_idname = "sf.subdivide_class1"
    bl_label = "Auto Subdivide (SM/NS Scenario)"

    def execute(self, context):
        count, scenario = self.apply_smart_subdivision()
        self.report({'INFO'}, f"[{scenario} 시나리오] Subdivision 적용 완료: {count}개")
        return {'FINISHED'}

    def apply_smart_subdivision(self):
        # 1. 씬 안의 모든 폴리곤 메쉬 수집
        meshes = [obj for obj in bpy.data.objects if obj.type == 'MESH']
        
        # 2. 패턴 분석 (디텍팅)
        sm_count = sum(1 for obj in meshes if obj.name.lower().endswith('_sm_geo'))
        ns_count = sum(1 for obj in meshes if obj.name.lower().endswith('_ns_geo'))
        
        print(f"[Subdivide Detect] _sm_geo 발견: {sm_count}개 / _ns_geo 발견: {ns_count}개")

        # 3. 시나리오 결정
        # ns_geo가 1개라도 있고(또는 다량 검출되고) sm_geo보다 많거나 같다면 NS 시나리오로 진입
        if ns_count > 0 and ns_count >= sm_count:
            scenario = "NS"
            print("[Subdivide] 👉 NS(No Smooth) 시나리오로 진행합니다.")
        else:
            scenario = "SM"
            print("[Subdivide] 👉 SM(Smooth) 시나리오로 진행합니다.")
            
        # 4. 시나리오별 스무스 실행
        count = 0
        for obj in meshes:
            name_low = obj.name.lower()
            
            if scenario == "SM":
                # [SM 시나리오] : _sm_geo 꼬리표가 붙은 메쉬만 스무스 적용
                if name_low.endswith('_sm_geo'):
                    if self.apply_subdivision(obj):
                        count += 1
                        
            elif scenario == "NS":
                # [NS 시나리오] : _ns_geo 꼬리표가 붙은 메쉬는 건너뛰고(Skip), 나머지 '_geo' 메쉬에 모두 스무스 적용
                # (안전장치: 씬 내의 쓰레기 메쉬에 스무스가 걸리는 걸 막기 위해 기본적으로 _geo로 끝나는 것들만 타겟팅합니다)
                if name_low.endswith('_geo') and not name_low.endswith('_ns_geo'):
                    if self.apply_subdivision(obj):
                        count += 1
                        
        return count, scenario

    def apply_subdivision(self, obj):
        # 중복 적용 방지
        if not any(mod.type == 'SUBSURF' for mod in obj.modifiers):
            mod = obj.modifiers.new(name="Subdivision", type='SUBSURF')
            mod.levels = 2
            mod.render_levels = 2
            mod.boundary_smooth = 'PRESERVE_CORNERS'
            print(f"  [✔] Subdivision 적용됨: {obj.name}")
            return True
        else:
            print(f"  [Skip] Subdivision 이미 존재함: {obj.name}")
            return False



        
class SF_OT_CreateCharacterLights(bpy.types.Operator):
    bl_idname = "object.sf_create_character_lights"
    bl_label = "Create Character Lights"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        import os
        from math import radians

        scene = context.scene
        category = scene.ldv_browser_tool.category

        # 현재 파일명에서 asset_name 추출
        asset_name = get_current_scene_asset_name()

        # 카테고리별 상위 컬렉션 이름
        main_col_name = {
            "ch": "ch_col",
            "bg": "bg_col",
            "prop": "prop_col"
        }.get(category)

        if not main_col_name:
            self.report({'ERROR'}, f"알 수 없는 카테고리: {category}")
            return {'CANCELLED'}

        # 상위 컬렉션 준비
        if main_col_name not in bpy.data.collections:
            main_col = bpy.data.collections.new(main_col_name)
            bpy.context.scene.collection.children.link(main_col)
        else:
            main_col = bpy.data.collections[main_col_name]

        # 라이트 전용 컬렉션
        light_col_name = f"{asset_name}_light_col"
        if light_col_name not in bpy.data.collections:
            light_col = bpy.data.collections.new(light_col_name)
            main_col.children.link(light_col)
        else:
            light_col = bpy.data.collections[light_col_name]

        # 라이트 Empty
        empty_name = f"{asset_name}_light"
        old = bpy.data.objects.get(empty_name)
        if old:
            bpy.data.objects.remove(old, do_unlink=True)

        light_empty = bpy.data.objects.new(empty_name, None)
        light_empty.empty_display_type = 'PLAIN_AXES'
        light_empty.location = (0, 0, 0)
        light_col.objects.link(light_empty)

        # 라이트 정보
        lights_info = [
            ("key", "SUN", 3, (0.01, -0.56, 1.7)),
            ("spec", "AREA", 5, (-0.58, -1.57, 1.23))
        ]

        for suffix, light_type, energy, location in lights_info:
            light_name = f"{asset_name}_light_{suffix}"

            # 기존 라이트 제거
            if bpy.data.lights.get(light_name):
                bpy.data.lights.remove(bpy.data.lights[light_name])
            if bpy.data.objects.get(light_name):
                bpy.data.objects.remove(bpy.data.objects[light_name], do_unlink=True)

            light_data = bpy.data.lights.new(name=light_name, type=light_type)
            light_obj = bpy.data.objects.new(name=light_name, object_data=light_data)
            light_obj.location = location
            light_obj.parent = light_empty
            light_col.objects.link(light_obj)

            light_data.energy = energy

            # 공통 shadow bias
            if hasattr(light_data, "shadow_bias"):
                light_data.shadow_bias = 0.03
            if scene.render.engine == 'BLENDER_EEVEE' and hasattr(light_data, "use_contact_shadow"):
                light_data.use_contact_shadow = True

            # 개별 설정
            if suffix == "key":
                light_data.diffuse_factor = 1
                light_data.volume_factor = 0
                light_data.specular_factor = 1
                light_data.use_shadow = True

                # ✅ Eevee Next 호환 (Sun Light 세팅)
                if hasattr(light_data, "use_contact_shadow"):
                    light_data.use_contact_shadow = False
                if hasattr(light_data, "shadow_cascade_max_distance"):
                    light_data.shadow_cascade_max_distance = 5.0   # 500cm
                if hasattr(light_data, "shadow_buffer_bias"):
                    light_data.shadow_buffer_bias = 0.03

                light_obj.rotation_euler[0] = 0.526



            elif suffix == "spec":
                light_data.shape = 'RECTANGLE'
                light_data.size = 0.5
                light_data.size_y = 0.5
                light_data.diffuse_factor = 0
                light_data.volume_factor = 0
                light_data.specular_factor = 1
                light_data.use_shadow = False

                # ✅ 공통 속성 안전 처리
                if hasattr(light_data, "shadow_bias"):
                    light_data.shadow_bias = 0.03
                if hasattr(light_data, "cutoff_distance"):
                    light_data.cutoff_distance = 5.0   # 500cm
                if hasattr(light_data, "use_custom_distance"):
                    light_data.use_custom_distance = True

                light_obj.rotation_euler[0] = 0.526   # 라디안 단위


        return {'FINISHED'}

            

def apply_textures_from_json_ch(asset_name):
    import json
    import os

    def clean_anim_path(path):
        parts = path.replace("\\", "/").split("/")
        cleaned_parts = [p for p in parts if p.lower() not in {"anim", "ani"}]
        return "/".join(cleaned_parts)

    _, category = get_assets()
    base_path = get_project_path()
    json_path = os.path.join(get_scene_asset_mod_dir(category, asset_name), "usd", f"{asset_name}.json")

    print(f"[DEBUG] [CH] JSON 경로: {json_path}")

    if not os.path.exists(json_path):
        print(f"[ERROR] [CH] JSON 파일 없음: {json_path}")
        return

    with open(json_path, "r") as f:
        data = json.load(f)

    for mesh in data.get("meshes", []):
        for mat_data in mesh.get("materials", []):
            mat_name = mat_data.get("name")
            mat = bpy.data.materials.get(mat_name)
            if not mat or not mat.use_nodes:
                continue

            nodes = mat.node_tree.nodes
            layers = mat_data.get("layers", [])
            if not layers:
                continue

            layer = layers[0]

            # Diffuse
            diffuse_path = layer.get("Diffuse") or layer.get("textures", {}).get("Diffuse")
            if diffuse_path:
                cleaned_path = clean_anim_path(diffuse_path)
                print(f"[PATH CLEAN] {mat_name} Diffuse: {diffuse_path} → {cleaned_path}")
                diffuse_path = cleaned_path

            if diffuse_path:
                try:
                    if "<UDIM>" in diffuse_path:
                        img = bpy.data.images.new(name=f"{mat_name}_UDIM", width=1024, height=1024)
                        img.source = 'TILED'
                        img.filepath = diffuse_path
                        img.reload()
                    else:
                        img = bpy.data.images.load(diffuse_path, check_existing=True)
                    diffuse_node = next((n for n in nodes if n.type == 'TEX_IMAGE' and n.label == "Diffuse"), None)
                    if diffuse_node:
                        diffuse_node.image = img
                        print(f"[OK] {mat_name} Diffuse 적용: {img.name}")
                except Exception as e:
                    print(f"[ERROR] {mat_name} Diffuse 로드 실패: {e}")

            # Normal
            normal_path = layer.get("Normal") or layer.get("textures", {}).get("Normal")
            if normal_path:
                cleaned_path = clean_anim_path(normal_path)
                print(f"[PATH CLEAN] {mat_name} Normal: {normal_path} → {cleaned_path}")
                normal_path = cleaned_path

            if normal_path:
                try:
                    img_normal = bpy.data.images.load(normal_path, check_existing=True)
                    normal_node = next((n for n in nodes if n.type == 'TEX_IMAGE' and n.label == "Normal"), None)
                    if normal_node:
                        normal_node.image = img_normal
                        normal_node.image.colorspace_settings.name = 'Non-Color'
                        print(f"[OK] {mat_name} Normal 적용: {img_normal.name}")
                except Exception as e:
                    print(f"[ERROR] {mat_name} Normal 로드 실패: {e}")

            # cornea Alpha
            if "cornea" in mat_name.lower():
                for layer in mat_data.get("layers", []):
                    alpha_path = layer.get("Alpha")
                    if alpha_path:
                        cleaned_path = clean_anim_path(alpha_path)
                        print(f"[PATH CLEAN] {mat_name} cornea Alpha: {alpha_path} → {cleaned_path}")
                        alpha_path = cleaned_path
                        try:
                            img_alpha = bpy.data.images.load(alpha_path, check_existing=True)
                            diffuse_node = next(
                                (n for n in nodes if n.type == 'TEX_IMAGE' and n.label == "Diffuse"), None
                            )
                            if diffuse_node:
                                diffuse_node.image = img_alpha
                                diffuse_node.image.colorspace_settings.name = 'sRGB'
                                print(f"[OK] {mat_name} cornea Alpha 적용: {img_alpha.name}")
                        except Exception as e:
                            print(f"[ERROR] {mat_name} cornea Alpha 로드 실패: {e}")

            # RGB 컬러
            if "color" in mat_data:
                color_val = mat_data["color"]
                rgb_node = next((n for n in nodes if n.type == 'RGB' and n.name == "RGB"), None)
                if rgb_node:
                    rgb_node.outputs[0].default_value = (*color_val, 1.0)
                    print(f"[OK] {mat_name} RGB 컬러 적용: {color_val}")


# =============================
# BG/PROP 카테고리용
# =============================
def clean_anim_path_generic(path):
    parts = path.replace("\\", "/").split("/")
    cleaned_parts = [p for p in parts if p.lower() not in {"anim", "ani"}]
    return "/".join(cleaned_parts)

def apply_textures_from_json(asset_name, category):
    import json
    import os

    # 기존 경로 얻는 부분은 그대로...
    base_path = get_project_path()
    json_path = os.path.join(get_scene_asset_mod_dir(category, asset_name), "usd", f"{asset_name}.json")

    if not os.path.exists(json_path):
        print(f"[JSON 없음] {json_path}")
        return

    with open(json_path, "r") as f:
        data = json.load(f)

    for mesh in data.get("meshes", []):
        for mat_data in mesh.get("materials", []):
            mat_name = mat_data.get("name")
            if not mat_name:
                continue

            mat = bpy.data.materials.get(mat_name)
            if not mat or not mat.use_nodes:
                continue
            nodes = mat.node_tree.nodes
            links = mat.node_tree.links
            sf_node = next((n for n in nodes if n.type == 'GROUP' and n.node_tree and any(key in n.node_tree.name.lower() for key in ["SF_Paint", "sf_toon_v03"])), None)
            if not sf_node:
                print(f"[SKIP] {mat_name} - SF_paint 노드 없음")
                continue

            layer = None
            layers = mat_data.get("layers", [])
            if layers:
                layer = layers[0]
            textures = layer.get("textures", {}) if layer else {}

            # ✅ Diffuse 텍스처 처리
            if "Diffuse" in textures:
                try:
                    tex_path = clean_anim_path_generic(textures["Diffuse"])
                    image_node = nodes.new("ShaderNodeTexImage")
                    image_node.image = bpy.data.images.load(tex_path)
                    image_node.image.colorspace_settings.name = 'sRGB'
                    image_node.label = "Diffuse"

                    tex_input = sf_node.inputs.get("Texture")
                    if tex_input:
                        if tex_input.is_linked:
                            for link in list(tex_input.links):
                                mat.node_tree.links.remove(link)
                        links.new(image_node.outputs["Color"], tex_input)
                        print(f"[OK] {mat_name} 텍스처 연결됨: {tex_path}")
                except:
                    print(f"[FAIL] 텍스처 로딩 실패: {textures['Diffuse']}")

            # ✅ RGB 컬러 적용
            if "color" in mat_data:
                rgb_node = next((n for n in nodes if n.type == 'RGB' and n.name == "RGB"), None)
                if rgb_node:
                    rgb_node.outputs[0].default_value = (*mat_data["color"], 1.0)
                    print(f"[OK] {mat_name} RGB 컬러 적용: {mat_data['color']}")
                else:
                    print(f"[SKIP] {mat_name} - RGB 노드 없음")

            
def unlink_all_outputs_from_node(node):
    links = list(node.id_data.links)
    for link in links:
        if link.from_node == node:
            try:
                node.id_data.links.remove(link)
            except RuntimeError:
                pass  # 이미 삭제된 링크일 수 있으므로 예외 무시



def get_basename(name):
    return name.rsplit(".", 1)[0] if "." in name and name.rsplit(".", 1)[1].isdigit() else name

def set_active_collection(asset_name):
    """
    asset_name_col 컬렉션을 찾아 context.view_layer.active_layer_collection을 설정
    """
    target_col_name = f"{asset_name}_col"
    scene = bpy.context.scene
    view_layer = bpy.context.view_layer

    def find_layer_collection(layer_coll, coll_name):
        if layer_coll.collection.name == coll_name:
            return layer_coll
        for child in layer_coll.children:
            found = find_layer_collection(child, coll_name)
            if found:
                return found
        return None

    layer_collection = find_layer_collection(view_layer.layer_collection, target_col_name)
    if layer_collection:
        view_layer.active_layer_collection = layer_collection
        print(f"[INFO] Active collection set to '{target_col_name}'")
    else:
        print(f"[WARNING] Collection '{target_col_name}' not found in view layer.")


class SF_ImportUSDOperator(bpy.types.Operator):
    bl_idname = "object.sf_import_usd_operator"
    bl_label = "Auto Import USD"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        filepath = bpy.data.filepath.replace("\\", "/")
        filename = os.path.splitext(os.path.basename(filepath))[0]
        asset_name = get_current_scene_asset_name()
        use_existing = context.scene.sf_mat_switcher.use_existing_materials
        # 활성 컬렉션 설정
        set_active_collection(asset_name)

        # USD 경로
        usd_path = os.path.join(
            get_scene_asset_mod_dir(get_assets()[1], asset_name), "usd", f"{asset_name}.usd"
        )

        if not os.path.exists(usd_path):
            self.report({'ERROR'}, f"USD 파일이 없습니다: {usd_path}")
            return {'CANCELLED'}

        # ✅ USD import
        major, minor = bpy.app.version[:2]

        usd_import_args = dict(
            filepath=usd_path,
            import_materials=True,
            import_usd_preview=False,
            import_all_materials=False,
            import_meshes=True,
            read_mesh_uvs=True,
            read_mesh_colors=True,
            scale=0.01  # 항상 0.01 적용
        )

        # Blender 4.2 이상일 때만 유닛 컨버전 끄기
        if (major, minor) >= (4, 4):
            usd_import_args["apply_unit_conversion_scale"] = False
        bpy.ops.wm.usd_import(**usd_import_args)
        
        # category, target, blend_path
        _, category = get_assets()
        targets = [obj for obj in bpy.context.selected_objects if obj.type == 'MESH']
        blend_path = resolve_script_path("blend", "ldvLight_v03.blend")

        # ✅ category == ch 순서적용
        if category == "ch":
            apply_matching_materials()
            apply_auto_materials_ch(targets, blend_path, asset_name, category)
        else:
            apply_matching_materials()
            apply_auto_materials(targets)

            # ✅ shader가 NEW일 경우에만 json 적용
            if not use_existing:
                all_material_names = {mat.name.rsplit(".", 1)[0] for mat in bpy.data.materials}
                apply_json_to_material_subset(all_material_names)

        bpy.ops.sf.subdivide_class1()
        # self.scale_root_empty()

        self.report({'INFO'}, f"USD + JSON 자동 재질 구성 완료 for {asset_name}")
        return {'FINISHED'}


    # def scale_root_empty(self):
        # root_obj = next((obj for obj in bpy.context.selected_objects if obj.type == 'EMPTY' and obj.parent is None), None)
        # if root_obj:
            # root_obj.scale = (0.01, 0.01, 0.01)

class SF_ImportUSDOperator(bpy.types.Operator):
    bl_idname = "object.sf_import_usd_operator"
    bl_label = "Auto Import USD"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        filepath = bpy.data.filepath.replace("\\", "/")
        filename = os.path.splitext(os.path.basename(filepath))[0]
        asset_name = get_current_scene_asset_name()
        use_existing = context.scene.sf_mat_switcher.use_existing_materials
        # 활성 컬렉션 설정
        set_active_collection(asset_name)

        # USD 경로
        usd_path = os.path.join(
            get_scene_asset_mod_dir(get_assets()[1], asset_name), "usd", f"{asset_name}.usd"
        )

        if not os.path.exists(usd_path):
            self.report({'ERROR'}, f"USD 파일이 없습니다: {usd_path}")
            return {'CANCELLED'}

        # ✅ USD import
        major, minor = bpy.app.version[:2]

        usd_import_args = dict(
            filepath=usd_path,
            import_materials=True,
            import_usd_preview=False,
            import_all_materials=False,
            import_meshes=True,
            read_mesh_uvs=True,
            read_mesh_colors=True,
            scale=0.01  # 항상 0.01 적용
        )

        # Blender 4.2 이상일 때만 유닛 컨버전 끄기
        if (major, minor) >= (4, 4):
            usd_import_args["apply_unit_conversion_scale"] = False
        bpy.ops.wm.usd_import(**usd_import_args)
        
        # category, target, blend_path
        _, category = get_assets()
        targets = [obj for obj in bpy.context.selected_objects if obj.type == 'MESH']
        blend_path = resolve_script_path("blend", "ldvLight_v03.blend")

        # ✅ category == ch 순서적용
        if category == "ch":
            apply_matching_materials()
            apply_auto_materials_ch(targets, blend_path, asset_name, category)
        else:
            apply_matching_materials()
            apply_auto_materials(targets)

            # ✅ shader가 NEW일 경우에만 json 적용
            if not use_existing:
                all_material_names = {mat.name.rsplit(".", 1)[0] for mat in bpy.data.materials}
                apply_json_to_material_subset(all_material_names)

        bpy.ops.sf.subdivide_class1()
        # self.scale_root_empty()

        self.report({'INFO'}, f"USD + JSON 자동 재질 구성 완료 for {asset_name}")
        return {'FINISHED'}


    # def scale_root_empty(self):
        # root_obj = next((obj for obj in bpy.context.selected_objects if obj.type == 'EMPTY' and obj.parent is None), None)
        # if root_obj:
            # root_obj.scale = (0.01, 0.01, 0.01)

       
class SF_ReplaceAssetOperator(bpy.types.Operator):
    bl_idname = "object.sf_replace_asset_operator"
    bl_label = "Replace Asset"
    
    def execute(self, context):
        scene = context.scene
        category = scene.my_asset_tool.category
        asset_name = scene.my_asset_tool.asset_name
        base_path = get_project_path()
        
        usd_filepath = os.path.join(get_scene_asset_mod_dir(category, asset_name), "usd", f"{asset_name}.usd")
        
        try:
            # 1. 원본 어셋 임포트
            bpy.ops.simple.import_usd(filepath=usd_filepath)
            
            # 2. 씬 어셋 컬렉션 찾기
            scene_collection_name = f"{asset_name}_col"
            scene_collection = bpy.data.collections.get(scene_collection_name)
            
            if scene_collection is None:
                self.report({'WARNING'}, f"Scene collection '{scene_collection_name}' not found")
                return {'CANCELLED'}
            
            # 3. 씬 어셋 찾기 (Mesh 오브젝트만, 이름 형식이 어셋이름_으로 시작해서 _geo로 끝나는)
            scene_assets = [obj for obj in scene_collection.objects if obj.type == 'MESH' and obj.name.startswith(asset_name) and obj.name.endswith('_geo')]
            
            if not scene_assets:
                self.report({'WARNING'}, f"No mesh objects matching the naming convention found in collection '{scene_collection_name}'")
                return {'CANCELLED'}
            
            # 4. 임포트된 원본 어셋 찾기 (Mesh 오브젝트만, 이름 형식이 어셋이름_으로 시작해서 _geo로 끝나는)
            imported_assets = [obj for obj in bpy.context.selected_objects if obj.type == 'MESH' and obj.name.startswith(asset_name) and obj.name.endswith('_geo')]
            
            if not imported_assets:
                self.report({'WARNING'}, f"Imported asset '{asset_name}_*_geo' not found")
                return {'CANCELLED'}
            
            # 5. 씬 어셋의 버텍스 데이터와 UV 맵을 원본 어셋에서 교체
            for scene_asset in scene_assets:
                imported_asset = next((obj for obj in imported_assets if obj.name.split('.')[0] == scene_asset.name.split('.')[0]), None)
                
                if imported_asset:
                    scene_mesh = scene_asset.data
                    imported_mesh = imported_asset.data

                    # 버텍스 위치 데이터 교체
                    scene_mesh.vertices.foreach_set("co", [co for vertex in imported_mesh.vertices for co in vertex.co])
                    
                    # UV 맵 교체
                    if scene_mesh.uv_layers.active and imported_mesh.uv_layers.active:
                        scene_uv_layer = scene_mesh.uv_layers.active.data
                        imported_uv_layer = imported_mesh.uv_layers.active.data
                        
                        scene_uv_layer.foreach_set("uv", [uv for uv_data in imported_uv_layer for uv in uv_data.uv])
                    
                    # 버텍스 인덱스와 면 정보 교체
                    scene_mesh.loops.foreach_set("vertex_index", [loop.vertex_index for loop in imported_mesh.loops])
                    scene_mesh.polygons.foreach_set("loop_start", [poly.loop_start for poly in imported_mesh.polygons])
                    scene_mesh.polygons.foreach_set("loop_total", [poly.loop_total for poly in imported_mesh.polygons])
                    
                    scene_mesh.update()
            
            # 임포트된 원본 어셋 삭제
            for imported_asset in imported_assets:
                bpy.data.objects.remove(imported_asset, do_unlink=True)
            
            self.report({'INFO'}, "Asset replaced successfully")
            return {'FINISHED'}
        
        except Exception as e:
            self.report({'WARNING'}, f"Asset replace failed: {str(e)}")
            return {'CANCELLED'}

def find_layer_collection(layer_collection, name):
    """LayerCollection 트리에서 이름으로 탐색"""
    if layer_collection.name == name:
        return layer_collection
    for child in layer_collection.children:
        found = find_layer_collection(child, name)
        if found:
            return found
    return None


class SF_OT_AddOutline(bpy.types.Operator):
    bl_idname = "object.sf_add_outline"
    bl_label = "Add Outline (geo 아래 MESH만)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        added_count = 0
        updated_cache_count = 0
        line_collections_created = 0
        linearts_created = 0

        for obj in bpy.data.objects:
            if obj.type != 'MESH':
                continue

            # --- obj가 속한 상위 컬렉션에서 asset_name 추출 ---
            parent_col = next((col for col in obj.users_collection if col.name.endswith("_col")), None)
            if not parent_col:
                continue
            asset_name = parent_col.name[:-4]  # "_col" 제거

            # --- 버텍스 그룹 추가 (outlineDel만) ---
            if "outlineDel" not in obj.vertex_groups.keys():
                obj.vertex_groups.new(name="outlineDel")
                added_count += 1

            # --- MeshSequenceCache 모디파이어 세팅 (있을 경우만) ---
            msc = obj.modifiers.get("MeshSequenceCache")
            if msc:
                msc.read_data = {'VERT', 'UV', 'COLOR'}
                updated_cache_count += 1

            # --- ch_col 밑에 {asset_name}_line_col 생성 ---
            line_col_name = f"{asset_name}_line_col"
            line_obj_name = f"{asset_name}_line"

            ch_col = bpy.data.collections.get("ch_col")
            if not ch_col:
                self.report({'WARNING'}, "'ch_col' 컬렉션 없음, 건너뜀")
                continue

            line_col = bpy.data.collections.get(line_col_name)
            if not line_col:
                line_col = bpy.data.collections.new(line_col_name)
                ch_col.children.link(line_col)
                line_collections_created += 1
                print(f"[INFO] '{line_col_name}' 컬렉션을 'ch_col' 하위에 생성 완료")

            # --- Grease Pencil Line Art 객체 생성 ---
            if not bpy.data.objects.get(line_obj_name):
                # 현재 활성 LayerCollection 저장
                prev_layer_collection = context.view_layer.active_layer_collection

                # {asset_name}_line_col LayerCollection 찾기
                line_layer = find_layer_collection(context.view_layer.layer_collection, line_col_name)
                if not line_layer:
                    self.report({'WARNING'}, f"'{line_col_name}' LayerCollection을 찾지 못했습니다.")
                    continue

                # ✅ {asset_name}_line_col을 active로 설정
                context.view_layer.active_layer_collection = line_layer

                # 라인아트 오브젝트 생성
                bpy.ops.object.gpencil_add(
                    align='WORLD',
                    location=(0, 0, 0),
                    scale=(1, 1, 1),
                    type='LRT_COLLECTION'
                )
                gp_obj = context.active_object
                gp_obj.name = line_obj_name
                linearts_created += 1

                # outlineDel 버텍스 그룹 생성
                if "outlineDel" not in gp_obj.vertex_groups.keys():
                    gp_obj.vertex_groups.new(name="outlineDel")

                # Line Art modifier 가져오기
                mod = gp_obj.grease_pencil_modifiers.get("Line Art")
                if mod:
                    mod.source_type = 'COLLECTION'
                    mod.source_collection = ch_col
                    mod.target_layer = "Lines"
                    mod.thickness = 1
                    mod.opacity = 1

                    mod.use_contour = True
                    mod.silhouette_filtering = 'NONE'
                    mod.use_intersection = False
                    mod.use_crease = True
                    mod.use_material = False
                    mod.use_edge_mark = True
                    mod.use_loose = True
                    mod.use_light_contour = False
                    mod.use_shadow = False
                    mod.use_overlap_edge_type_support = True
                    mod.source_vertex_group = "outlineDel"
                    mod.use_output_vertex_group_match_by_name = True

                # --- Opacity 모디파이어 추가 ---
                bpy.context.view_layer.objects.active = gp_obj
                bpy.ops.object.gpencil_modifier_add(type='GP_OPACITY')
                op_mod = gp_obj.grease_pencil_modifiers.get("Opacity")
                if op_mod:
                    op_mod.use_weight_factor = True
                    op_mod.modify_color = 'STROKE'
                    op_mod.vertex_group = "outlineDel"
                    op_mod.invert_vertex = True

                # --- GP 데이터 세팅 ---
                gp_obj.data.stroke_thickness_space = 'SCREENSPACE'
                gp_obj.data.pixel_factor = 2

                # 원래 활성 컬렉션 복원
                context.view_layer.active_layer_collection = prev_layer_collection

            obj.data.update()

        context.view_layer.update()

        self.report(
            {'INFO'},
            f"✅ 버텍스 그룹 {added_count}개 추가, "
            f"MeshSequenceCache {updated_cache_count}개 업데이트, "
            f"line_col {line_collections_created}개 생성, "
            f"LineArt {linearts_created}개 생성"
        )
        return {'FINISHED'}



class SF_OT_SetOutlineWeight(bpy.types.Operator):
    """선택한 오브젝트의 outlineDel 그룹 웨이트를 0 또는 1로 설정"""
    bl_idname = "object.sf_set_outline_weight"
    bl_label = "Set OutlineDel Weight"
    bl_options = {'REGISTER', 'UNDO'}

    value: bpy.props.FloatProperty(default=0.0)

    def execute(self, context):
        for obj in context.selected_objects:
            if obj.type == 'MESH' and "outlineDel" in obj.vertex_groups:
                vg = obj.vertex_groups["outlineDel"]
                for v in obj.data.vertices:
                    vg.add([v.index], self.value, 'REPLACE')
        self.report({'INFO'}, f"outlineDel → {self.value}")
        return {'FINISHED'}





class SF_OT_RefreshDrivers(bpy.types.Operator):
    bl_idname = "scene.refresh_drivers"
    bl_label = "Refresh Drivers"
    bl_description = "Force re-evaluate all drivers (objects, materials, world)"

    def execute(self, context):

        def ensure_object_in_view_layer(obj):
            scene = bpy.context.scene
            view_layer = bpy.context.view_layer

            if obj.name not in scene.collection.all_objects:
                for coll in bpy.data.collections:
                    if obj.name in coll.objects and coll.name not in scene.collection.children:
                        scene.collection.children.link(coll)
                        break
                if obj.name not in scene.collection.objects:
                    scene.collection.objects.link(obj)

            if obj.name not in view_layer.objects:
                print(f"[⚠] {obj.name} → View Layer에 없음 (드라이버 작동안함)")
            else:
                print(f"[✔] {obj.name} → View Layer에 있음")

        def update_driver_expression(driver_fcurve):
            for var in driver_fcurve.driver.variables:
                for target in var.targets:
                    if target.id and isinstance(target.id, bpy.types.Object):
                        ensure_object_in_view_layer(target.id)
                        all_targets.add(target.id)

            driver_fcurve.driver.expression += " "
            driver_fcurve.driver.expression = driver_fcurve.driver.expression[:-1]

        def jiggle_custom_properties(obj):
            for key in obj.keys():
                value = obj[key]
                try:
                    if isinstance(value, float):
                        obj[key] += 0.00001
                        obj[key] -= 0.00001
                    elif isinstance(value, bpy.types.IDPropertyArray) and len(value) > 0:
                        old_val = value[0]
                        value[0] = old_val + 0.00001
                        value[0] = old_val
                except:
                    continue

        all_targets = set()

        try:
            # 오브젝트 드라이버
            for obj in bpy.data.objects:
                ad = obj.animation_data
                if ad and ad.drivers:
                    for fc in ad.drivers:
                        update_driver_expression(fc)

            # 머티리얼 노드 트리 드라이버
            for mat in bpy.data.materials:
                nt = mat.node_tree
                if nt and nt.animation_data and nt.animation_data.drivers:
                    for fc in nt.animation_data.drivers:
                        update_driver_expression(fc)

            # 월드 노드 트리 드라이버
            for world in bpy.data.worlds:
                nt = world.node_tree
                if nt and nt.animation_data and nt.animation_data.drivers:
                    for fc in nt.animation_data.drivers:
                        update_driver_expression(fc)

            # 타겟 오브젝트 jiggle
            for obj in all_targets:
                jiggle_custom_properties(obj)

            # 종속성 그래프 갱신
            depsgraph = context.evaluated_depsgraph_get()
            depsgraph.update()
            context.view_layer.update()

            self.report({'INFO'}, f"{len(all_targets)}개의 드라이버 타겟을 jiggle하고 리프레시했습니다.")
            return {'FINISHED'}

        except Exception as e:
            self.report({'WARNING'}, f"드라이버 리프레시 실패: {e}")
            return {'CANCELLED'}


LOOKDEV_MATERIALS = [
    "auto_all",
    "MI_cloth", "MI_eyeBrow", "MI_skin", "MI_cornea",
    "MI_eyeWhite", "MI_eyeBall", "MI_hair", "MI_teeth"
]


class SF_MaterialSwitcherProperties(bpy.types.PropertyGroup):
    mat_choices: bpy.props.EnumProperty(
        name="Material",
        description="Choose LookDev Material",
        items=[(mat, mat, "") for mat in LOOKDEV_MATERIALS],
        default="MI_cloth"
    )

    use_existing_materials: bpy.props.BoolProperty(
        name="Use Existing Materials",  # ✅ 문법도 깔끔하게
        description="Skip automatic material override on import",
        default=False
    )


class SF_OT_SwitchLookdevMaterial(bpy.types.Operator):
    bl_idname = "sf.switch_lookdev_material"
    bl_label = "Switch LookDev Material"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        selected = context.scene.sf_mat_switcher.mat_choices
        auto_mode = selected.lower() == "auto all"
        blend_path = resolve_script_path("blend", "ldvLight_v03.blend")

        # 대상 오브젝트 추출
        if auto_mode:
            assets, _ = get_assets()
            targets = []
            for asset_name, _, _ in assets:
                col = bpy.data.collections.get(f"{asset_name}_col")
                if col:
                    targets.extend([obj for obj in col.objects if obj.type == 'MESH'])
        else:
            targets = [obj for obj in context.selected_objects if obj.type == 'MESH']

        # ✅ auto_all이면 None, 아니면 직접 선택한 메터리얼 이름 넘김
        force_mat = None if auto_mode else selected

        replaced_count = apply_auto_materials(targets, blend_path, force_material_name=force_mat)
        self.report({'INFO'}, f"{replaced_count} material(s) replaced.")
        return {'FINISHED'}

class SF_OT_ParentLightToTurntable(bpy.types.Operator):
    bl_idname = "object.sf_parent_light_to_turntable"
    bl_label = "Parent Light to Turntable"
    bl_description = "라이트 어셋을 턴어셋에 페어런트 시킵니다 (Keep Transform)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # 1. chLdv_Light 컬렉션에서 턴테이블 엠티 검색
        turntable = None
        for obj in bpy.data.collections.get("chLdv_Light", {}).objects:
            if obj.name.startswith("chLdv_Light") and obj.type == 'EMPTY':
                turntable = obj
                break

        if not turntable:
            self.report({'ERROR'}, "chLdv_Light 내 턴어셋 엠티를 찾을 수 없습니다.")
            return {'CANCELLED'}

        # 2. 현재 에셋 이름 추출
        asset_name = get_current_scene_asset_name()

        # 3. 어셋 라이트 컬렉션 검색
        light_col_name = f"{asset_name}_light_col"
        light_obj = None
        if light_col_name in bpy.data.collections:
            for obj in bpy.data.collections[light_col_name].objects:
                if obj.name.startswith(f"{asset_name}_light") and obj.type == 'EMPTY':
                    light_obj = obj
                    break

        if not light_obj:
            self.report({'ERROR'}, f"{light_col_name} 내 라이트 엠티를 찾을 수 없습니다.")
            return {'CANCELLED'}

        # 4. 페어런트 (Keep Transform)
        light_obj.parent = turntable
        light_obj.matrix_parent_inverse = turntable.matrix_world.inverted()

        self.report({'INFO'}, f"{light_obj.name} → {turntable.name} 페어런트 완료")
        return {'FINISHED'}
        
class SF_OT_CleanupMaterialNodes(bpy.types.Operator):
    bl_idname = "sf.cleanup_material_nodes"
    bl_label = "Cleanup Nodes & Adjust Toon"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        asset_info = get_assets()
        if not asset_info or not asset_info[1]:
            self.report({'ERROR'}, "카테고리 정보 없음 (get_assets 실패)")
            return {'CANCELLED'}

        category = asset_info[1]

        def delete_node_preserve_links(tree, node):
            input_links = [link for input in node.inputs for link in input.links]
            output_links = [link for output in node.outputs for link in output.links]
            for in_link in input_links:
                for out_link in output_links:
                    try:
                        tree.links.new(in_link.from_socket, out_link.to_socket)
                    except:
                        pass
            tree.nodes.remove(node)

        def process_node_tree(tree):
            if not tree:
                return
            for node in list(tree.nodes):
                is_sffilmic = (
                    (node.type == 'GROUP' and node.node_tree and node.node_tree.name.startswith("SF_Filmic")) or
                    node.name.startswith("SF_Filmic") or
                    node.label.startswith("SF_Filmic")
                )
                if is_sffilmic:
                    delete_node_preserve_links(tree, node)
                    continue

                if node.type == 'GROUP' and node.node_tree and node.node_tree.name == "SF_Toon_v03":
                    if "Hue" in node.inputs:
                        node.inputs["Hue"].default_value = 0.5
                    if "Saturation" in node.inputs:
                        node.inputs["Saturation"].default_value = 1.0
                    if "Value" in node.inputs:
                        node.inputs["Value"].default_value = 1.0

        used_mats = set()
        for obj in bpy.context.scene.objects:
            if obj.type == 'MESH':
                for slot in obj.material_slots:
                    if slot.material:
                        used_mats.add(slot.material)

        for mat in used_mats:
            if mat.use_nodes:
                process_node_tree(mat.node_tree)

        for node_group in bpy.data.node_groups:
            process_node_tree(node_group)

        # ✅ ch 카테고리일 때만 씬 트랜스폼 변경
        if category == "ch":
            bpy.context.scene.view_settings.view_transform = "Standard"
            self.report({'INFO'}, "뷰 트랜스폼을 Standard로 설정했습니다.")

        self.report({'INFO'}, "머티리얼 정리 및 SF_Toon 조정 완료")
        return {'FINISHED'}

class LDV_OT_OpenEmptyFile(bpy.types.Operator):
    bl_idname = "ldv.open_empty_file"
    bl_label = "Open Empty"

    def execute(self, context):
        tool = context.scene.ldv_browser_tool
        project, category, asset = tool.project, tool.category, tool.asset_enum

        if not asset or asset == 'NONE':
            self.report({'ERROR'}, "No asset selected.")
            return {'CANCELLED'}

        target_dir = get_project_blend_dir(project, category, asset)
        os.makedirs(target_dir, exist_ok=True)

        empty_path = os.path.join(target_dir, f"{asset}_v000.blend")

        bpy.ops.wm.save_as_mainfile(filepath=empty_path, copy=True)  # 현재 씬을 v000으로 저장 (복사 저장)
        bpy.ops.wm.open_mainfile(filepath=empty_path)                # v000 파일 열기

        return {'FINISHED'}
        

class SF_OT_SetLayerOperator(bpy.types.Operator):
    bl_idname = "object.sf_set_layer_operator"
    bl_label = "Set Layer"

    def execute(self, context):
        layer_name = context.scene.layer_name_input.strip()
        if not layer_name:
            self.report({'ERROR'}, "Please enter a name for the layer.")
            return {'CANCELLED'}

        assets, category = get_assets()
        if not assets:
            self.report({'ERROR'}, "Unable to determine asset name.")
            return {'CANCELLED'}

        asset_name = assets[0][0]
        parent_col_name = f"{asset_name}_col"
        sub_col_name = f"{layer_name}_col"

        parent_col = bpy.data.collections.get(parent_col_name)
        if not parent_col:
            self.report({'ERROR'}, f"Parent collection '{parent_col_name}' not found.")
            return {'CANCELLED'}

        sub_col = bpy.data.collections.get(sub_col_name)
        if not sub_col:
            sub_col = bpy.data.collections.new(sub_col_name)
        if sub_col.name not in parent_col.children:
            parent_col.children.link(sub_col)

        # 선택된 오브젝트 이동
        for obj in context.selected_objects:
            # 다른 컬렉션에서 제거
            for c in obj.users_collection:
                c.objects.unlink(obj)
            # 대상 컬렉션으로 이동
            sub_col.objects.link(obj)

        self.report({'INFO'}, f"Moved to {sub_col_name}")
        return {'FINISHED'}

def get_light_presets(self, context):
    items = []
    assets, category = get_assets()
    if not assets or category != "bg":
        return [("NONE", "No Preset", "", 0)]

    asset_name = assets[0][0]
    base_dir = os.path.join(get_project_path(), "assets", category, asset_name, "lgt")

    if not os.path.exists(base_dir):
        return [("NONE", "No lgt folder", "", 0)]

    blend_files = [f for f in os.listdir(base_dir) if f.endswith(".blend")]
    if not blend_files:
        return [("NONE", "No Presets Found", "", 0)]

    for i, f in enumerate(sorted(blend_files)):
        name = os.path.splitext(f)[0]
        items.append((name, name, "", '', i))

    return items


class SF_OT_ImportSelectedLightPreset(bpy.types.Operator):
    bl_idname = "sf.import_selected_light_preset"
    bl_label = "Import Selected Light Preset"
    bl_description = "프리셋에서 라이트 오브젝트만 불러와 *_light_col을 만들고 bg_col 하위에 배치합니다."

    def execute(self, context):
        preset_name = context.scene.light_preset_choice
        if not preset_name or preset_name == "NONE":
            self.report({'ERROR'}, "프리셋이 선택되지 않았습니다.")
            return {'CANCELLED'}

        if not preset_name.endswith("_lgt"):
            self.report({'ERROR'}, "유효한 프리셋 이름이 아닙니다.")
            return {'CANCELLED'}

        assets, category = get_assets()
        if not assets or category != "bg":
            self.report({'ERROR'}, "BG 카테고리에서만 사용 가능합니다.")
            return {'CANCELLED'}

        asset_name = assets[0][0]
        preset_path = os.path.join(
            get_project_path(), "assets", category, asset_name, "lgt", f"{preset_name}.blend"
        )

        if not os.path.exists(preset_path):
            self.report({'ERROR'}, f"프리셋 파일이 존재하지 않습니다:\n{preset_path}")
            return {'CANCELLED'}

        light_col_name = f"{asset_name}_light_col"

        # ✅ 이미 존재하면 로드하지 않음
        if light_col_name in bpy.data.collections:
            self.report({'INFO'}, f"'{light_col_name}' 컬렉션이 이미 존재합니다.")
            return {'CANCELLED'}

        try:
            # ✅ 오브젝트만 불러오기
            with bpy.data.libraries.load(preset_path, link=False) as (data_from, data_to):
                data_to.objects = data_from.objects

            # ✅ 라이트 컬렉션 생성
            light_col = bpy.data.collections.new(light_col_name)

            # ✅ bg_col 확보 및 연결
            bg_col = bpy.data.collections.get("bg_col")
            if not bg_col:
                bg_col = bpy.data.collections.new("bg_col")
                context.scene.collection.children.link(bg_col)

            bg_col.children.link(light_col)

            # ✅ 오브젝트 링크 (중복 방지 + 중복 unlink)
            for obj in data_to.objects:
                if obj:
                    # 다른 컬렉션에서 제거
                    for col in obj.users_collection:
                        col.objects.unlink(obj)
                    # light_col에만 추가
                    light_col.objects.link(obj)

            self.report({'INFO'}, f"'{light_col_name}' 프리셋 적용 완료.")
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"프리셋 임포트 실패: {e}")
            return {'CANCELLED'}



class SF_OT_DeleteLightPresetCollection(bpy.types.Operator):
    bl_idname = "sf.delete_selected_light_preset"
    bl_label = "Delete Light Preset"
    bl_description = "선택한 프리셋이 만든 *_light_col 컬렉션을 씬에서 삭제합니다."

    def execute(self, context):
        preset_name = context.scene.light_preset_choice

        if not preset_name.endswith("_lgt"):
            self.report({'ERROR'}, "유효한 프리셋 이름이 아닙니다.")
            return {'CANCELLED'}

        target_col_name = preset_name.replace("_lgt", "_light_col")
        coll = bpy.data.collections.get(target_col_name)
        if not coll:
            self.report({'WARNING'}, f"'{target_col_name}' 컬렉션이 존재하지 않습니다.")
            return {'CANCELLED'}

        # 모든 부모 컬렉션에서 언링크
        for parent in bpy.data.collections:
            if coll.name in parent.children:
                parent.children.unlink(coll)

        if coll.users == 0:
            bpy.data.collections.remove(coll)
            self.report({'INFO'}, f"'{target_col_name}' 컬렉션 삭제 완료.")
        else:
            self.report({'WARNING'}, f"'{target_col_name}'는 아직 사용 중입니다.")

        return {'FINISHED'}



import platform
import subprocess

class SF_OT_OpenAssetFolder(bpy.types.Operator):
    bl_idname = "sf.open_asset_folder"
    bl_label = "Open Asset Folder"
    bl_description = "선택한 어셋의 에셋 폴더를 파일 탐색기로 엽니다."

    def execute(self, context):
        tool = context.scene.ldv_browser_tool
        project, category, asset = tool.project, tool.category, tool.asset_enum

        if not asset or asset == "NONE":
            self.report({'ERROR'}, "에셋이 선택되지 않았습니다.")
            return {'CANCELLED'}

        folder_path = get_project_asset_dir(project, category, asset)

        if not os.path.exists(folder_path):
            self.report({'ERROR'}, f"경로가 존재하지 않습니다:\n{folder_path}")
            return {'CANCELLED'}

        try:
            system = platform.system()
            if system == "Windows":
                os.startfile(folder_path)
            elif system == "Darwin":
                subprocess.Popen(["open", folder_path])
            else:  # Linux
                subprocess.Popen(["xdg-open", folder_path])
        except Exception as e:
            self.report({'ERROR'}, f"폴더 열기 실패: {e}")
            return {'CANCELLED'}

        self.report({'INFO'}, f"폴더 열림: {folder_path}")
        return {'FINISHED'}

import tempfile
import shutil
class SF_OT_SaveLightPreset(bpy.types.Operator):
    bl_idname = "sf.save_light_preset"
    bl_label = "Save Light Preset"
    bl_description = "light_col을 씬에 연결한 뒤 프리셋으로 저장하고, 다시 bg_col 하위로 복원합니다."

    def execute(self, context):
        assets, category = get_assets()
        if not assets or category != "bg":
            self.report({'ERROR'}, "BG 카테고리에서만 사용 가능합니다.")
            return {'CANCELLED'}

        asset_name = assets[0][0]
        light_col = bpy.data.collections.get(f"{asset_name}_light_col")
        if not light_col:
            self.report({'ERROR'}, "light_col 컬렉션이 없습니다.")
            return {'CANCELLED'}

        # 🎯 대상 오브젝트: light_col 안의 Light/Camera
        objs = {obj for obj in light_col.all_objects if obj.type in {'LIGHT', 'CAMERA'}}
        if not objs:
            self.report({'WARNING'}, "light_col에 저장할 라이트/카메라가 없습니다.")
            return {'CANCELLED'}

        export_dir = os.path.join(get_project_path(), "assets", category, asset_name, "lgt")
        os.makedirs(export_dir, exist_ok=True)
        export_path = os.path.join(export_dir, f"{asset_name}_lgt.blend")

        # ✅ 기존 연결 정보 저장
        originally_linked_to_scene = light_col.name in context.scene.collection.children
        bg_col = bpy.data.collections.get("bg_col")
        was_under_bg_col = bg_col and light_col.name in bg_col.children

        # ✅ 1. 씬에 연결 (없으면 추가)
        if not originally_linked_to_scene:
            context.scene.collection.children.link(light_col)

        # ✅ 2. 저장
        try:
            bpy.data.libraries.write(
                filepath=export_path,
                datablocks=objs | {light_col},
                fake_user=True
            )
        except Exception as e:
            self.report({'ERROR'}, f"프리셋 저장 실패: {e}")
            return {'CANCELLED'}

        # ✅ 3. 씬에서 연결 제거 (조건적으로)
        if not originally_linked_to_scene:
            context.scene.collection.children.unlink(light_col)

        # ✅ 4. bg_col에 원래 있었으면 다시 연결
        if was_under_bg_col and bg_col:
            if light_col.name not in bg_col.children:
                bg_col.children.link(light_col)

        self.report({'INFO'}, f"프리셋 저장 완료:\n{export_path}")
        return {'FINISHED'}




class SF_OT_OpenLightPresetPrompt(bpy.types.Operator):
    bl_idname = "sf.open_light_preset_prompt"
    bl_label = "Open Light Preset"
    bl_description = "프리셋 파일 또는 폴더를 엽니다."

    choice: bpy.props.EnumProperty(
        name="Open Mode",
        items=[
            ('FILE', "Open File", "Blender에서 프리셋 파일 열기"),
            ('FOLDER', "Open Folder", "탐색기에서 폴더 열기")
        ],
        default='FOLDER'
    )

    def execute(self, context):
        assets, category = get_assets()
        if not assets or category != "bg":
            self.report({'ERROR'}, "BG 카테고리에서만 사용 가능합니다.")
            return {'CANCELLED'}

        asset_name = assets[0][0]
        preset_path = os.path.join(
            get_project_path(), "assets", category, asset_name, "lgt", f"{asset_name}_lgt.blend"
        )
        folder_path = os.path.dirname(preset_path)

        if self.choice == 'FILE':
            if os.path.exists(preset_path):
                bpy.ops.wm.open_mainfile(filepath=preset_path)
            else:
                self.report({'ERROR'}, f"프리셋 파일이 없습니다:\n{preset_path}")
                return {'CANCELLED'}

        elif self.choice == 'FOLDER':
            if not os.path.exists(folder_path):
                self.report({'ERROR'}, f"폴더가 없습니다:\n{folder_path}")
                return {'CANCELLED'}

            import platform, subprocess
            if platform.system() == "Windows":
                os.startfile(folder_path)
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", folder_path])
            else:
                subprocess.Popen(["xdg-open", folder_path])

        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        self.layout.label(text="프리셋 파일을 열까요, 아니면 폴더를 열까요?")
        self.layout.prop(self, "choice", expand=True)

# ✅ 경로 및 유틸
import os
import json
import bpy

SF_PAINT_PRESET_PATH = resolve_preset_path("sf_paint_presets.json")
os.makedirs(os.path.dirname(SF_PAINT_PRESET_PATH), exist_ok=True)

def load_sf_paint_presets():
    if not os.path.exists(SF_PAINT_PRESET_PATH):
        return {}
    with open(SF_PAINT_PRESET_PATH, 'r') as f:
        return json.load(f)

def save_sf_paint_presets(presets):
    with open(SF_PAINT_PRESET_PATH, 'w') as f:
        json.dump(presets, f, indent=2)

# ✅ SF_Paint 파라미터 추출 및 적용
def extract_sf_paint_values_from_material(mat):
    if not mat or not mat.use_nodes:
        return None
    group = next(
        (n for n in mat.node_tree.nodes
         if n.type == 'GROUP' and n.node_tree and n.node_tree.name.startswith("SF_Paint")),
        None
    )
    if not group:
        return None
    keys = ["Metallic", "Roughness", "IOR", "Alpha", "Transmission"]
    return {k: group.inputs[k].default_value for k in keys if k in group.inputs}

def apply_sf_paint_values_to_material(mat, values):
    if not mat or not mat.use_nodes:
        print(f"[SKIP] {mat.name}: use_nodes = False")
        return
    group = next(
        (n for n in mat.node_tree.nodes
         if n.type == 'GROUP' and n.node_tree and n.node_tree.name.startswith("SF_Paint")),
        None
    )
    if not group:
        print(f"[SKIP] {mat.name}: No SF_Paint node group found")
        return

    print(f"[✔ APPLYING] {mat.name} ← {group.name}")
    for k, v in values.items():
        if k in group.inputs:
            print(f"   - {k}: {group.inputs[k].default_value} → {v}")
            group.inputs[k].default_value = v
        else:
            print(f"   [⚠] Input '{k}' not found in '{group.name}'")

# ✅ EnumProperty
class SFPaintPresetProperties(bpy.types.PropertyGroup):
    preset_list: bpy.props.EnumProperty(
        name="Preset",
        items=lambda self, ctx: [(k, k, "") for k in load_sf_paint_presets().keys()]
    )

# ✅ New 버튼 → 팝업
class SF_OT_SaveSFPaintPresetPopup(bpy.types.Operator):
    bl_idname = "sf.save_sf_paint_preset_popup"
    bl_label = "Save SF_Paint Preset"
    bl_options = {'REGISTER', 'UNDO'}

    preset_name: bpy.props.StringProperty(name="Preset Name")

    def execute(self, context):
        presets = load_sf_paint_presets()
        values = None

        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue
            for slot in obj.material_slots:
                mat = slot.material
                values = extract_sf_paint_values_from_material(mat)
                if values:
                    break
            if values:
                break

        if not values:
            self.report({'WARNING'}, "No SF_Paint material found in selection.")
            return {'CANCELLED'}

        presets[self.preset_name] = values
        save_sf_paint_presets(presets)
        self.report({'INFO'}, f"Preset '{self.preset_name}' saved.")
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

# ✅ Assign 버튼
class SF_OT_AssignSFPaintPreset(bpy.types.Operator):
    bl_idname = "sf.assign_sf_paint_preset"
    bl_label = "Assign SF_Paint Preset"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        preset_name = context.scene.sf_paint_presets.preset_list
        presets = load_sf_paint_presets()
        values = presets.get(preset_name)

        if not values:
            self.report({'ERROR'}, "Preset not found.")
            return {'CANCELLED'}

        count = 0
        for obj in context.selected_objects:
            if obj.type != 'MESH' or not obj.active_material:
                continue

            # ✅ 현재 active slot의 material만 대상
            mat = obj.active_material
            apply_sf_paint_values_to_material(mat, values)
            count += 1

        self.report({'INFO'}, f"Preset '{preset_name}' applied to {count} material(s).")
        return {'FINISHED'}


# ✅ 등록 함수
def register_sf_paint_presets():
    bpy.utils.register_class(SFPaintPresetProperties)
    bpy.utils.register_class(SF_OT_SaveSFPaintPresetPopup)
    bpy.utils.register_class(SF_OT_AssignSFPaintPreset)
    bpy.types.Scene.sf_paint_presets = bpy.props.PointerProperty(type=SFPaintPresetProperties)

def unregister_sf_paint_presets():
    bpy.utils.unregister_class(SFPaintPresetProperties)
    bpy.utils.unregister_class(SF_OT_SaveSFPaintPresetPopup)
    bpy.utils.unregister_class(SF_OT_AssignSFPaintPreset)
    del bpy.types.Scene.sf_paint_presets

class LDV_OT_AutoImportPopup(bpy.types.Operator):
    bl_idname = "ldv.auto_import_popup"
    bl_label = "Auto Import Shader Option"

    def execute(self, context):
        return {'FINISHED'}

    def invoke(self, context, event):
        def draw(self, context):
            layout = self.layout
            layout.label(text="Choose Shader Import Mode:")
            layout.operator("sf.auto_import_shader", text="New Shader").mode = 'NEW'
            layout.operator("sf.auto_import_shader", text="Use Existing Shader").mode = 'EXISTING'

        context.window_manager.popup_menu(draw, title="Auto Import", icon='IMPORT')
        return {'FINISHED'}

class SF_OT_AutoImportShader(bpy.types.Operator):
    bl_idname = "sf.auto_import_shader"
    bl_label = "Auto Import Shader"

    mode: bpy.props.EnumProperty(
        name="Shader Mode",
        items=[
            ('NEW', "New Shader", ""),
            ('EXISTING', "Use Existing Shader", "")
        ]
    )

    def execute(self, context):
        use_existing = (self.mode == 'EXISTING')
        context.scene.sf_mat_switcher.use_existing_materials = use_existing

        # Auto Import 실행
        bpy.ops.object.sf_import_usd_operator('INVOKE_DEFAULT')
        return {'FINISHED'}

class LDV_OT_ManualImportPopup(bpy.types.Operator):
    bl_idname = "ldv.manual_import_popup"
    bl_label = "Manual Import Format"

    def execute(self, context):
        return {'FINISHED'}

    def invoke(self, context, event):
        def draw(self, context):
            layout = self.layout
            layout.label(text="Choose Import Format:")
            layout.operator("simple.import_fbx", text="FBX Import", icon='IMPORT')
            layout.operator("simple.import_usd", text="USD Import", icon='IMPORT')

        context.window_manager.popup_menu(draw, title="Manual Import", icon='IMPORT')
        return {'FINISHED'}

class SF_OT_ConvertPrincipledToSFPaint(bpy.types.Operator):
    bl_idname = "object.sf_convert_principled_to_paint"
    bl_label = "Convert Principled to SF_Out (Selected Only)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        import os

        if not context.selected_objects:
            self.report({'WARNING'}, "선택된 오브젝트가 없습니다.")
            return {'CANCELLED'}

        # SF_Out 노드그룹 로드
        blend_path = resolve_script_path("blend", "SF_Paint.blend")
        group_name = "SF_Out"
        if group_name not in bpy.data.node_groups:
            with bpy.data.libraries.load(blend_path, link=False) as (data_from, data_to):
                if group_name in data_from.node_groups:
                    data_to.node_groups = [group_name]

        sf_out_group = bpy.data.node_groups.get(group_name)
        if not sf_out_group:
            self.report({'ERROR'}, f"SF_Out 노드그룹을 불러올 수 없습니다: {blend_path}")
            return {'CANCELLED'}

        replaced = 0
        mats = set()

        for obj in context.selected_objects:
            for slot in obj.material_slots:
                if slot.material:
                    mats.add(slot.material)

        for mat in mats:
            if not mat.use_nodes:
                continue

            nodes = mat.node_tree.nodes
            links = mat.node_tree.links

            for node in list(nodes):
                if node.type != 'BSDF_PRINCIPLED':
                    continue

                # 입력 링크/값 백업
                input_map = {}
                for inp in node.inputs:
                    if inp.is_linked and inp.links:
                        input_map[inp.name] = ('LINK', inp.links[0].from_socket)
                    else:
                        try:
                            input_map[inp.name] = ('VALUE', inp.default_value)
                        except:
                            pass

                # 출력 링크 백업
                output_map = {}
                for out in node.outputs:
                    if out.is_linked:
                        output_map[out.name] = [l.to_socket for l in out.links]

                # 위치 정보
                loc = node.location
                label = node.label
                mute = node.mute

                # Principled 삭제
                nodes.remove(node)

                # SF_Out 생성
                try:
                    new_node = nodes.new("ShaderNodeGroup")
                    new_node.node_tree = sf_out_group
                    new_node.location = loc
                    new_node.label = label
                    new_node.mute = mute
                except Exception as e:
                    print(f"[ERROR] SF_Out 노드 생성 실패: {e}")
                    continue

                # 입력 연결 복원
                for name, value in input_map.items():
                    if name not in new_node.inputs:
                        continue
                    try:
                        if value[0] == 'LINK':
                            links.new(value[1], new_node.inputs[name])
                        elif value[0] == 'VALUE':
                            target_input = new_node.inputs[name]
                            val = value[1]
                            if isinstance(target_input.default_value, float):
                                target_input.default_value = float(val)
                            elif isinstance(target_input.default_value, int):
                                target_input.default_value = int(val)
                            elif isinstance(target_input.default_value, (list, tuple)):
                                if isinstance(val, (list, tuple)) and len(val) == len(target_input.default_value):
                                    target_input.default_value = val
                    except Exception as e:
                        print(f"[WARN] 입력 복원 실패: {name} - {e}")

                # 출력 연결 복원
                for name, sockets in output_map.items():
                    if name not in new_node.outputs:
                        continue
                    for sock in sockets:
                        try:
                            links.new(new_node.outputs[name], sock)
                        except Exception as e:
                            print(f"[WARN] 출력 연결 실패: {name} - {e}")

                replaced += 1

        self.report({'INFO'}, f"{replaced}개의 노드가 SF_Out으로 교체되었습니다.")
        return {'FINISHED'}

def update_asset_list_cache(project_key):
    base_path = PROJECTS[project_key][1]  # ex: S:/assets
    result = {}

    for cat in CATEGORY_ITEMS:
        cat_key = cat[0]  # 'bg', 'ch', 'prop'
        if is_coc_project(project_key) and cat_key != COC_CATEGORY:
            continue

        cat_path = get_project_asset_root(project_key, cat_key)
        if not os.path.exists(cat_path):
            continue

        entries = []
        for name in os.listdir(cat_path):
            entry_path = os.path.join(cat_path, name)
            if not os.path.isdir(entry_path):
                continue
            if name.startswith("_") or name.startswith("."):
                continue
            if is_coc_project(project_key):
                if not os.path.exists(os.path.join(entry_path, "mod", "usd")):
                    continue
            entries.append(name)
        result[cat_key] = {entry: {} for entry in entries}

    cache_path = get_cache_path(project_key)
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)

    with open(cache_path, 'w') as f:
        json.dump(result, f, indent=2)

    print(f"[✔] assetList.json updated (filtered): {cache_path}")

class LDV_OT_AppendPublishedAsset(bpy.types.Operator):
    bl_idname = "ldv.append_published_asset"
    bl_label = "Append Published Asset"
    bl_description = "퍼블리시된 에셋을 현재 씬에 append 합니다"

    def execute(self, context):
        tool = context.scene.ldv_browser_tool
        project = tool.project
        category = tool.category
        asset = tool.asset_enum

        if not asset or asset == "NONE":
            self.report({'ERROR'}, "에셋이 선택되지 않았습니다.")
            return {'CANCELLED'}

        # .blend 경로
        blend_path = get_project_publish_blend_path(project, category, asset)
        if not os.path.exists(blend_path):
            self.report({'ERROR'}, f"파일이 존재하지 않습니다:\n{blend_path}")
            return {'CANCELLED'}

        # Append할 컬렉션 이름
        collection_name = f"{asset}_col"
        category_col_name = f"{category}_col"

        with bpy.data.libraries.load(blend_path, link=False) as (data_from, data_to):
            if collection_name in data_from.collections:
                data_to.collections = [collection_name]
            else:
                self.report({'ERROR'}, f"{collection_name} 컬렉션이 파일에 없습니다.")
                return {'CANCELLED'}

        # 연결
        asset_col = bpy.data.collections.get(collection_name)
        if not asset_col:
            self.report({'ERROR'}, f"{collection_name} 컬렉션 로드 실패")
            return {'CANCELLED'}

        category_col = bpy.data.collections.get(category_col_name)
        if not category_col:
            category_col = bpy.data.collections.new(category_col_name)
            context.scene.collection.children.link(category_col)

        if asset_col.name not in category_col.children:
            category_col.children.link(asset_col)

        self.report({'INFO'}, f"'{collection_name}' 컬렉션을 append했습니다.")
        return {'FINISHED'}

# === Goo Engine 체크 ===
def is_goo_engine():
    return "goo" in bpy.app.version_string.lower()


class OBJECT_OT_ConvertVGroupToColorC(bpy.types.Operator):
    """버텍스 그룹 → 컬러 어트리뷰트 변환"""
    bl_idname = "object.convert_vgroup_to_colorc"
    bl_label = "Convert VGroup to Color"
    bl_options = {'REGISTER', 'UNDO'}

    target_mode: bpy.props.EnumProperty(
        name="대상 범위",
        description="변환할 오브젝트 범위 선택",
        items=[
            ('SELECTED', "Selected Objects", "선택한 오브젝트만 변환"),
            ('ALL', "All Meshes", "씬 안의 모든 메쉬 변환")
        ],
        default='SELECTED'
    )

    color_name: bpy.props.StringProperty(
        name="Color Attribute",
        default="ToonkitLineID"
    )

    def invoke(self, context, event):
        # 버튼 클릭 시 팝업 띄우기
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "target_mode", expand=True)

    def execute(self, context):
        print(f"[DEBUG] === ConvertVGroupToColorC 실행 (mode={self.target_mode}) ===")

        # --- 대상 오브젝트 결정 ---
        if self.target_mode == 'ALL':
            objs = [obj for obj in bpy.data.objects if obj.type == 'MESH']
        else:
            objs = [obj for obj in context.selected_objects if obj.type == 'MESH']

        print(f"[DEBUG] 처리할 오브젝트 수: {len(objs)}")

        for obj in objs:
            mesh = obj.data
            color_name = self.color_name

            # 항상 Color Attribute 보장
            if color_name not in mesh.color_attributes:
                mesh.color_attributes.new(name=color_name, type='BYTE_COLOR', domain='POINT')
                print(f"[INFO] {obj.name}: '{color_name}' 생성")

            color_layer = mesh.color_attributes[color_name]

            # outlineDel 그룹 가져오기
            vg = obj.vertex_groups.get("outlineDel")

            if not vg:
                # 그룹 없으면 0 채움
                for i in range(len(color_layer.data)):
                    color_layer.data[i].color = (0.0, 0.0, 0.0, 1.0)
                print(f"[INFO] {obj.name}: outlineDel 없음 → 0으로 채움")
                continue

            # 그룹 있으면 변환
            for i, v in enumerate(mesh.vertices):
                try:
                    w = vg.weight(i)
                except RuntimeError:
                    w = 0.0
                color_layer.data[i].color = (w, w, w, 1.0)

            print(f"[INFO] {obj.name}: outlineDel → '{color_name}' 변환 완료")

        print("[DEBUG] === ConvertVGroupToColorC 실행 종료 ===")
        return {'FINISHED'}
        
import bpy
import mathutils
from mathutils import kdtree

def _strip_blender_numeric_suffix(name: str) -> str:
    if '.' in name and name.split('.')[-1].isdigit():
        return '.'.join(name.split('.')[:-1])
    return name

def _iter_mesh_descendants(root_obj):
    stack = [root_obj]
    while stack:
        o = stack.pop()
        for c in o.children:
            stack.append(c)
        if o.type == 'MESH':
            yield o


class FUZZ_OT_TransferFreestyleEdges(bpy.types.Operator):
    """먼저 선택한 오브젝트의 Freestyle 엣지를 타깃 오브젝트로 전이 (엣지 중점 기반, evaluated mesh 지원)
       - 두 Empty 선택 시: 각 하위 트리에서 같은 이름의 Mesh끼리 일괄 전이
       - Mesh Sequence / Alembic / Modifier 적용 후에도 좌표 보정 기반으로 정확히 전이
    """
    bl_idname = "object.fuzz_transfer_freestyle_edges"
    bl_label = "Transfer Freestyle Edges (by Edge Midpoint / Evaluated)"
    bl_options = {'REGISTER', 'UNDO'}

    distance: bpy.props.FloatProperty(
        name="Distance Threshold",
        description="엣지 중점 간 거리 허용 범위(월드 공간)",
        default=0.000001,
        min=0.0,
        precision=8
    )

    transfer_mode: bpy.props.EnumProperty(
        name="Match Mode",
        description="Freestyle edge? ?? ???? ??? ??",
        items=[
            ("TOPOLOGY", "Topology", "?? ????? edge index ???? ??"),
            ("DISTANCE", "Distance", "?? ?? ??? ??"),
            ("UV", "UV", "?? UV ?? ???? ??"),
        ],
        default="TOPOLOGY",
    )

    case_sensitive: bpy.props.BoolProperty(
        name="Case Sensitive Match",
        description="이름 매칭 시 대소문자 구분",
        default=False
    )

    def _name_key(self, name: str) -> str:
        base = _strip_blender_numeric_suffix(name)
        return base if self.case_sensitive else base.lower()


    def _edge_domain_is_edge(self, attr):
        domain = getattr(attr, "domain", None)
        if domain is None:
            return False
        return str(domain).upper() == "EDGE"

    def _get_bmesh_freestyle_layer(self, bm):
        try:
            layers = bm.edges.layers
        except Exception:
            return None

        freestyle_layers = getattr(layers, "freestyle", None)
        if freestyle_layers is None:
            return None

        for attr_name in ("active", "verify"):
            try:
                attr = getattr(freestyle_layers, attr_name)
            except Exception:
                attr = None
            if attr is None:
                continue
            try:
                return attr() if callable(attr) else attr
            except Exception:
                continue

        try:
            return freestyle_layers.new()
        except Exception:
            return None

    def _mesh_marked_edge_indices_bmesh(self, mesh):
        indices = set()
        if mesh is None:
            return indices

        if getattr(mesh, "is_editmode", False):
            try:
                bm = bmesh.from_edit_mesh(mesh)
                layer = self._get_bmesh_freestyle_layer(bm)
                if layer is None:
                    return indices
                bm.edges.ensure_lookup_table()
                for edge in bm.edges:
                    try:
                        if bool(edge[layer]):
                            indices.add(int(edge.index))
                    except Exception:
                        continue
                return indices
            except Exception:
                pass

        bm = bmesh.new()
        try:
            bm.from_mesh(mesh)
            layer = self._get_bmesh_freestyle_layer(bm)
            if layer is None:
                return indices
            bm.edges.ensure_lookup_table()
            for edge in bm.edges:
                try:
                    if bool(edge[layer]):
                        indices.add(int(edge.index))
                except Exception:
                    continue
        except Exception:
            return indices
        finally:
            try:
                bm.free()
            except Exception:
                pass
        return indices

    def _find_freestyle_edge_attribute(self, mesh):
        attributes = getattr(mesh, "attributes", None)
        if attributes is None:
            return None

        preferred_names = ("freestyle_edge", "use_freestyle_mark", "freestyle_mark")
        fallback = []
        try:
            fallback = list(attributes)
        except Exception:
            fallback = []

        for attr in fallback:
            name = getattr(attr, "name", "")
            if name in preferred_names and self._edge_domain_is_edge(attr):
                return attr

        for attr in fallback:
            name = getattr(attr, "name", "")
            lowered = name.lower()
            if ("freestyle" in lowered or "mark" in lowered) and self._edge_domain_is_edge(attr):
                return attr

        for name in preferred_names:
            try:
                attr = attributes.get(name)
            except Exception:
                attr = None
            if attr is not None and self._edge_domain_is_edge(attr):
                return attr

        return None

    def _edge_signature(self, edge):
        try:
            return tuple(sorted((int(edge.vertices[0]), int(edge.vertices[1]))))
        except Exception:
            return None

    def _uv_signature(self, mesh, edge):
        try:
            uv_layer = getattr(mesh.uv_layers, "active", None)
            if uv_layer is None:
                return None
            data = uv_layer.data
            uv_a = None
            uv_b = None
            for loop in mesh.loops:
                if loop.vertex_index == edge.vertices[0]:
                    uv_a = tuple(round(v, 6) for v in data[loop.index].uv)
                elif loop.vertex_index == edge.vertices[1]:
                    uv_b = tuple(round(v, 6) for v in data[loop.index].uv)
                if uv_a and uv_b:
                    break
            if not uv_a or not uv_b:
                return None
            return tuple(sorted((uv_a, uv_b)))
        except Exception:
            return None
    def _edge_has_freestyle_mark(self, mesh, edge):
        if hasattr(edge, "use_freestyle_mark"):
            return bool(edge.use_freestyle_mark)
        attr = self._find_freestyle_edge_attribute(mesh)
        if attr is not None:
            try:
                return bool(attr.data[edge.index].value)
            except Exception:
                pass
        marked_indices = self._mesh_marked_edge_indices_bmesh(mesh)
        if marked_indices:
            return int(edge.index) in marked_indices
        return False

    def _set_edge_freestyle_mark(self, mesh, edge_index, value=True):
        if mesh is None or edge_index < 0:
            return False

        try:
            edge = mesh.edges[edge_index]
        except Exception:
            edge = None

        if edge is not None and hasattr(edge, "use_freestyle_mark"):
            edge.use_freestyle_mark = bool(value)
            return True

        attributes = getattr(mesh, "attributes", None)
        if attributes is None:
            return False

        freestyle_attr = self._find_freestyle_edge_attribute(mesh)
        if freestyle_attr is None:
            for attr_name in ("freestyle_edge", "use_freestyle_mark"):
                try:
                    freestyle_attr = attributes.new(name=attr_name, type='BOOLEAN', domain='EDGE')
                    break
                except Exception:
                    freestyle_attr = None
            if freestyle_attr is None:
                return False

        try:
            freestyle_attr.data[edge_index].value = bool(value)
            try:
                mesh.update()
            except Exception:
                pass
            return True
        except Exception:
            pass

        if getattr(mesh, "is_editmode", False):
            try:
                bm = bmesh.from_edit_mesh(mesh)
                bm.edges.ensure_lookup_table()
                if edge_index >= len(bm.edges):
                    return False
                layer = self._get_bmesh_freestyle_layer(bm)
                if layer is None:
                    return False
                bm.edges[edge_index][layer] = bool(value)
                bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
                return True
            except Exception:
                pass

        bm = bmesh.new()
        try:
            bm.from_mesh(mesh)
            bm.edges.ensure_lookup_table()
            if edge_index >= len(bm.edges):
                return False
            layer = self._get_bmesh_freestyle_layer(bm)
            if layer is None:
                return False
            bm.edges[edge_index][layer] = bool(value)
            bm.to_mesh(mesh)
            try:
                mesh.update()
            except Exception:
                pass
            return True
        except Exception:
            return False
        finally:
            try:
                bm.free()
            except Exception:
                pass

    def _edge_mark_indices(self, mesh):
        indices = set()
        if mesh is None:
            return indices
        try:
            for edge in mesh.edges:
                if self._edge_has_freestyle_mark(mesh, edge):
                    indices.add(int(edge.index))
        except Exception:
            pass
        if indices:
            return indices
        return self._mesh_marked_edge_indices_bmesh(mesh)

    def _collect_marked_edges(self, mesh_candidates):
        for mesh in mesh_candidates:
            if mesh is None:
                continue
            try:
                marked_indices = self._edge_mark_indices(mesh)
                marked = [mesh.edges[i] for i in sorted(marked_indices) if i < len(mesh.edges)]
            except Exception:
                marked = []
            if marked:
                return mesh, marked
        return None, []

    def _transfer_edges_via_data_transfer(self, src, tgt, edge_mapping="TOPOLOGY"):
        if src is None or tgt is None or src.type != 'MESH' or tgt.type != 'MESH':
            return 0

        prev_active = None
        prev_selected = []
        prev_mode = None
        try:
            prev_active = bpy.context.view_layer.objects.active
        except Exception:
            prev_active = None
        try:
            prev_selected = list(bpy.context.selected_objects)
        except Exception:
            prev_selected = []
        try:
            prev_mode = bpy.context.mode
        except Exception:
            prev_mode = None

        before_indices = self._edge_mark_indices(tgt.data)

        try:
            if prev_mode and prev_mode != 'OBJECT':
                try:
                    bpy.ops.object.mode_set(mode='OBJECT')
                except Exception:
                    pass

            for obj in prev_selected:
                try:
                    obj.select_set(False)
                except Exception:
                    pass

            try:
                src.select_set(True)
                tgt.select_set(True)
            except Exception:
                pass

            try:
                bpy.context.view_layer.objects.active = src
            except Exception:
                pass

            override_kwargs = {
                "active_object": src,
                "object": src,
                "selected_objects": [src, tgt],
                "selected_editable_objects": [src, tgt],
            }
            try:
                override_kwargs["view_layer"] = bpy.context.view_layer
            except Exception:
                pass

            try:
                with bpy.context.temp_override(**override_kwargs):
                    bpy.ops.object.data_transfer(
                        data_type='FREESTYLE_EDGE',
                        edge_mapping=edge_mapping,
                        use_reverse_transfer=False,
                        use_freeze=True,
                    )
            except TypeError:
                with bpy.context.temp_override(**override_kwargs):
                    bpy.ops.object.data_transfer(
                        data_type='FREESTYLE_EDGE',
                        edge_mapping=edge_mapping,
                        use_reverse_transfer=False,
                    )
            except Exception:
                return 0

            after_indices = self._edge_mark_indices(tgt.data)
            return len(after_indices.difference(before_indices))
        finally:
            try:
                for obj in bpy.context.selected_objects:
                    obj.select_set(False)
            except Exception:
                pass
            for obj in prev_selected:
                try:
                    obj.select_set(True)
                except Exception:
                    pass
            try:
                bpy.context.view_layer.objects.active = prev_active
            except Exception:
                pass
            if prev_mode and prev_mode != 'OBJECT':
                try:
                    bpy.ops.object.mode_set(mode=prev_mode)
                except Exception:
                    pass

    def transfer_edges_pair(self, src, tgt):
        if self.transfer_mode == "UV":
            return self._transfer_edges_by_uv(src, tgt)
        if self.transfer_mode == "TOPOLOGY":
            copied = self._transfer_edges_via_data_transfer(src, tgt, edge_mapping="TOPOLOGY")
            if copied > 0:
                return copied
            return self._transfer_edges_by_topology(src, tgt)
        if self.transfer_mode == "DISTANCE":
            copied = self._transfer_edges_via_data_transfer(src, tgt, edge_mapping="NEAREST")
            if copied > 0:
                return copied
            return self._transfer_edges_by_distance(src, tgt)
        return 0

    def _transfer_edges_by_topology(self, src, tgt):
        depsgraph = bpy.context.evaluated_depsgraph_get()
        src_eval = src.evaluated_get(depsgraph)
        tgt_eval = tgt.evaluated_get(depsgraph)
        src_eval_mesh = src_eval.to_mesh()
        tgt_eval_mesh = tgt_eval.to_mesh()

        src_mesh = src.data
        tgt_mesh = tgt.data
        _, marked_src_edges = self._collect_marked_edges((src_mesh, src_eval_mesh))
        if not marked_src_edges:
            src_eval.to_mesh_clear()
            tgt_eval.to_mesh_clear()
            return 0

        src_signatures = {self._edge_signature(e) for e in marked_src_edges}
        src_signatures.discard(None)
        if src_signatures and len(src_mesh.vertices) == len(tgt_mesh.vertices) and len(src_mesh.edges) == len(tgt_mesh.edges):
            copied = 0
            for e_tgt in tgt_mesh.edges:
                if self._edge_signature(e_tgt) in src_signatures:
                    if self._set_edge_freestyle_mark(tgt_mesh, e_tgt.index, True):
                        copied += 1
            src_eval.to_mesh_clear()
            tgt_eval.to_mesh_clear()
            if copied > 0:
                return copied
        src_eval.to_mesh_clear()
        tgt_eval.to_mesh_clear()
        return 0

    def _transfer_edges_by_distance(self, src, tgt, src_eval=None, tgt_eval=None, src_eval_mesh=None, tgt_eval_mesh=None):
        depsgraph = bpy.context.evaluated_depsgraph_get()
        src_eval = src_eval or src.evaluated_get(depsgraph)
        tgt_eval = tgt_eval or tgt.evaluated_get(depsgraph)
        src_eval_mesh = src_eval_mesh or src_eval.to_mesh()
        tgt_eval_mesh = tgt_eval_mesh or tgt_eval.to_mesh()

        src_world = src.matrix_world
        tgt_world = tgt.matrix_world
        src_mesh = src.data
        tgt_mesh = tgt.data

        _, marked_src_edges = self._collect_marked_edges((src_mesh, src_eval_mesh))
        if not marked_src_edges:
            src_eval.to_mesh_clear()
            tgt_eval.to_mesh_clear()
            return 0

        eval_verts = [src_world @ v.co for v in src_eval_mesh.vertices]
        kd = kdtree.KDTree(len(marked_src_edges))
        for e in marked_src_edges:
            try:
                v1, v2 = (eval_verts[e.vertices[0]], eval_verts[e.vertices[1]])
                mid = (v1 + v2) * 0.5
                kd.insert(mid, e.index)
            except:
                pass
        kd.balance()

        copied = 0
        for e_tgt in tgt_mesh.edges:
            try:
                v1, v2 = (tgt_world @ tgt_eval_mesh.vertices[e_tgt.vertices[0]].co,
                          tgt_world @ tgt_eval_mesh.vertices[e_tgt.vertices[1]].co)
                mid = (v1 + v2) * 0.5
                co, idx, dist = kd.find(mid)
                if dist < self.distance:
                    if self._set_edge_freestyle_mark(tgt_mesh, e_tgt.index, True):
                        copied += 1
            except:
                pass

        src_eval.to_mesh_clear()
        tgt_eval.to_mesh_clear()
        return copied

    def _transfer_edges_by_uv(self, src, tgt):
        depsgraph = bpy.context.evaluated_depsgraph_get()
        src_eval = src.evaluated_get(depsgraph)
        tgt_eval = tgt.evaluated_get(depsgraph)
        src_eval_mesh = src_eval.to_mesh()
        tgt_eval_mesh = tgt_eval.to_mesh()

        src_mesh = src.data
        tgt_mesh = tgt.data
        _, marked_src_edges = self._collect_marked_edges((src_mesh, src_eval_mesh))
        if not marked_src_edges:
            src_eval.to_mesh_clear()
            tgt_eval.to_mesh_clear()
            return 0

        src_signatures = {self._uv_signature(src_eval_mesh, e) for e in marked_src_edges}
        src_signatures.discard(None)
        if src_signatures and len(src_mesh.edges) == len(tgt_mesh.edges):
            copied = 0
            for e_tgt in tgt_mesh.edges:
                if self._uv_signature(tgt_eval_mesh, e_tgt) in src_signatures:
                    if self._set_edge_freestyle_mark(tgt_mesh, e_tgt.index, True):
                        copied += 1
            src_eval.to_mesh_clear()
            tgt_eval.to_mesh_clear()
            if copied > 0:
                return copied
        src_eval.to_mesh_clear()
        tgt_eval.to_mesh_clear()
        return 0

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=360)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "transfer_mode", expand=True)
        if self.transfer_mode == "DISTANCE":
            layout.prop(self, "distance")
        layout.prop(self, "case_sensitive")

    def _transfer_for_two_empties(self, src_empty, tgt_empty):
        src_meshes = list(_iter_mesh_descendants(src_empty))
        tgt_meshes = list(_iter_mesh_descendants(tgt_empty))

        tgt_by_key = {}
        for o in tgt_meshes:
            tgt_by_key.setdefault(self._name_key(o.name), []).append(o)

        total_pairs = 0
        total_edges = 0

        for s in src_meshes:
            key = self._name_key(s.name)
            candidates = tgt_by_key.get(key, [])
            if not candidates:
                continue
            t = candidates[0]
            copied = self.transfer_edges_pair(s, t)
            if copied > 0:
                total_pairs += 1
                total_edges += copied
                tgt_by_key[key].pop(0)
                if not tgt_by_key[key]:
                    del tgt_by_key[key]

        return total_pairs, total_edges

    def execute(self, context):
        sel = list(bpy.context.selected_objects)
        if len(sel) < 2:
            self.report({'ERROR'}, "⚠️ 최소 2개 오브젝트(소스, 타깃)를 선택하세요.")
            return {'CANCELLED'}

        src = sel[0]
        tgt = sel[-1]

        if src.type == 'EMPTY' and tgt.type == 'EMPTY':
            pairs, edges = self._transfer_for_two_empties(src, tgt)
            if self.transfer_mode == "DISTANCE":
                self.report({'INFO'}, f"[Batch][DISTANCE] {pairs} pairs, {edges} edges copied (threshold={self.distance})")
            else:
                self.report({'INFO'}, f"[Batch][{self.transfer_mode}] {pairs} pairs, {edges} edges copied")
            return {'FINISHED'}
            self.report({'INFO'}, f"[Batch] {pairs} 쌍 처리, {edges} 엣지 복사 (거리={self.distance})")
            return {'FINISHED'}

        if src.type != 'MESH' or tgt.type != 'MESH':
            self.report({'ERROR'}, "메쉬-메쉬 쌍이거나, 두 Empty(하위 일괄)만 지원합니다.")
            return {'CANCELLED'}

        copied = self.transfer_edges_pair(src, tgt)
        if self.transfer_mode == "DISTANCE":
            self.report({'INFO'}, f"[Single][DISTANCE] '{src.name}' -> '{tgt.name}': {copied} edges (threshold={self.distance})")
        else:
            self.report({'INFO'}, f"[Single][{self.transfer_mode}] '{src.name}' -> '{tgt.name}': {copied} edges")
        return {'FINISHED'}
        self.report({'INFO'}, f"[Single] '{src.name}' → '{tgt.name}': {copied} 엣지 (거리={self.distance})")
        return {'FINISHED'}


class SF_PT_LookDev2Panel(bpy.types.Panel):
    bl_label = "SF_Blender_LookDev_v2"
    bl_idname = "SF_PT_lookdev2_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "SF_LookDev"   # ← 여기!

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        tool = scene.ldv_browser_tool

        # LookDev Browser
        box = layout.box()
        # box.label(text="LookDev Browser", icon='FILE_FOLDER')
        row = box.row(align=True)
        row.operator("dev.reload_blendldv", icon="FILE_REFRESH")
        row.operator("ldv.open_project_setup_app", text="Setup", icon="PREFERENCES")
        row.operator("dev.deploy_blendldv", text="Deploy", icon="EXPORT")
        row = box.row(align=True)
        row.operator("ldv.project_prev", text="◀", emboss=False)
        col = row.column()
        col.alignment = 'CENTER'
        col.label(text=tool.project)
        row.operator("ldv.project_next", text="▶", emboss=False)     
        row = box.row()
        row.prop(tool, "category", expand=True)  # ← 이걸 반드시 row.prop으로
        box.template_icon_view(tool, "asset_enum", show_labels=True)
        row = box.row(align=True)
        # row.scale_y = 0.6
        row.scale_x = 1
        row.operator("ldv.refresh_gallery", text="", icon='FILE_REFRESH')
        row.operator("ldv.capture_thumbnail", text="", icon='RENDER_STILL')
        row.scale_x = 2
        row.prop(tool, "version_enum", text="")
        row.scale_x = 1
        row.operator("sf.open_asset_folder", text="", icon='FILE_FOLDER')
        row = box.row(align=True)
        row.scale_y = 1
        row.operator("ldv.confirm_action_dialog", text="New", icon='FILE_NEW').action = 'open_empty'
        row.operator("ldv.confirm_action_dialog", text="Open", icon='FILE_FOLDER').action = 'open_file'
        row.operator("ldv.append_published_asset", text="Append", icon='APPEND_BLEND')
        
        # 안전하게 category와 asset_name 추출
        assets, category = get_assets()
        if not assets:
            asset_name = "Unknown"
        else:
            asset_name = assets[0][0]

        # === LookDev Scene Builder ===
        box = layout.box()
        # box.label(text="LookDev Scene Builder", icon='SCENE_DATA')
        row = box.row()
        row.label(text="Current Asset :")
        row.label(text=asset_name)
        row = box.row()
        row.operator("ldv.confirm_action_dialog", text="Save +1", icon='FILE_TICK').action = 'save_incremental'
        row.operator("ldv.confirm_action_dialog", text="Publish", icon='EXPORT').action = 'publish'
        row = box.row()
        row.operator("object.sf_build_scene_operator", text="Build LookDev")


        # === Asset Importer ===
        box = layout.box()
        box.label(text="Asset Importer" , icon='IMPORT')

        row = box.row()
        row.scale_y = 1.5  # ✅ 버튼 높이 키움
        row.operator("ldv.auto_import_popup", text="Auto", icon='IMPORT')
        row.prop(context.scene, "manual_import_enabled", toggle=True, icon='IMPORT')
        
        # ✅ 체크된 경우만 버튼 보이기
        if context.scene.manual_import_enabled:
            row = box.row()
            row.operator("simple.import_fbx", text="FBX")
            row.operator("simple.import_usd", text="USD")        
        
        row = box.row()
        if category != "ch":
            row.operator("object.sf_convert_to_paint_shader", text="Reset Shader")
            row.operator("object.sf_convert_principled_to_paint", text="Make SF_Paint")


        box = layout.box()
        box.label(text="Set Sub Collection", icon='GROUP')

        row = box.row(align=True)
        row.scale_x = 1
        row.prop(context.scene, "layer_name_input", text="", icon='FILE_FOLDER')  # 70%
        row.scale_x = 0.4
        row.operator("object.sf_set_layer_operator", text="Set")  # 30%


        # === Light Section ===
        # === Light Section ===
        box = layout.box()
        box.label(text="Ch Light & Link" if category == "ch" else "Light Preset", icon='LIGHT')

        # 👉 bg만 프리셋 UI 표시
        if category == "bg":
            row = box.row(align=True)
            row.scale_x = 1
            row.prop(context.scene, "light_preset_choice", text="")
            row.scale_x = 1
            row.operator("sf.open_light_preset_prompt", text="", icon='FILE_FOLDER')
            row.operator("sf.save_light_preset", text="", icon='FILE_TICK')
            row = box.row(align=True)
            row.scale_x = 0.6            
            row.operator("sf.import_selected_light_preset", text="Load", icon='APPEND_BLEND')
            row.operator("sf.delete_selected_light_preset", text="Delete", icon='TRASH')

        # 👉 ch만 Update Shader 표시
        if category == "ch":
            row = box.row()
            row.operator("object.sf_load_and_link_nodegroup", text="1. Update Shader")
        # 👉 ch, prop만 2, 3번 표시
        if category in {"ch", "prop"}:
            row = box.row()
            row.operator("object.sf_create_character_lights", text="2. Make Light")
            row = box.row()
            row.operator("object.sf_add_properties_and_link", text="3. Make Ctrl")
            row = box.row()
            row.operator("object.set_character_light_and_outline", text="Fix ldv Scene")
            row = box.row()

        # === Outline Tools ===
        if category == "ch":

            box = layout.box()
            box.label(text="Outline Tools", icon='MOD_SOLIDIFY')
            # row = box.row()            
            # row.prop(context.scene, "outline_target_mode", expand=True)
            row = box.row()         
            row.operator("object.sf_add_outline", text="Make Lines")
            # row.operator("object.sf_remove_outline", text="Del")
            # sub = row.row(align=True)
            # sub.scale_x = 0.3
            # sub.operator("object.sf_set_outline_weight", text=" + ", icon='ADD').value = 0.0
            # sub.operator("object.sf_set_outline_weight", text=" - ", icon='REMOVE').value = 1.0
        # if category == "ch":
        box = layout.box()
        box.label(text="Turnaround", icon='OUTLINER_OB_ARMATURE') 
        row = box.row()
        row.operator("object.sf_lookdev_operator", text="Import")
        row.operator("object.sf_delete_lookdev_light_operator", text="delete") 
        row = box.row()
        row.operator("object.sf_parent_light_to_turntable", text="Link Light") 
        
        # --- ch 전용 Materials 섹션 ---
        if category == "ch":
            box = layout.box()
            box.label(text="Materials", icon='OUTLINER_OB_ARMATURE') 
            row = box.row()
            props = context.scene.sf_mat_switcher
            row.prop(props, "mat_choices", text="")
            row = box.row()
            row.operator("sf.apply_lookdev_material", text="Apply")   

        # --- bg/prop 전용 SF_Paint Presets 섹션 ---
        elif category in {"bg", "prop"}:
            box = layout.box()
            box.label(text="SF_Paint Presets", icon='SHADING_TEXTURE')
            row = box.row(align=True)
            row.prop(context.scene.sf_paint_presets, "preset_list", text="")
            row.operator("sf.save_sf_paint_preset_popup", text="", icon='ADD')
            row = box.row()
            row.operator("sf.assign_sf_paint_preset", text="Assign", icon='CHECKMARK')

     
        box = layout.box()
        box.label(text="Extra Tools", icon='TOOL_SETTINGS')
        row = box.row()
        row.operator("sf.cleanup_orphans_combined", text="CleanUp", icon='TRASH')         # 고아 데이터 정리
        row.operator("sf.reload_all_images", text="Texture", icon='FILE_REFRESH')      # 이미지 리로드
        row = box.row()
        row.operator("sf.cleanup_material_nodes", text="Fix ColorSpace", icon='NODE_MATERIAL')  # 너가 추가할 버튼
        row = box.row()
        row.operator("object.fuzz_transfer_freestyle_edges", icon="MOD_TRIANGULATE")


    def get_last_modified(self, file_path):
        try:
            mod_time = os.path.getmtime(file_path)
            return datetime.fromtimestamp(mod_time).strftime("%Y-%m-%d %H:%M")
        except OSError:
            return "File not found"
        
    
from bpy.utils import previews





# 썸네일 프리뷰 전역 변수
thumb_previews = None

# 모든 등록할 클래스 리스트
classes = [
    # LookDev Browser
    LdvBrowserProperties,
    LDV_OT_ProjectPrev,
    LDV_OT_ProjectNext,
    LDV_OT_RefreshGallery,
    LDV_OT_OpenProjectSetupApp,
    LDV_OT_CaptureThumbnail,
    LDV_OT_OpenBlendFile,
    LDV_OT_ConfirmActionDialog,
    LDV_OT_SaveAsV001,
    LDV_OT_SaveIncremental,
    
    # LookDev Operators, Panels 등
    SF_OT_AddOutline,
    SF_OT_SetOutlineWeight,
    SIMPLE_OT_import_fbx,
    SF_OT_LookDevOperator,
    SF_OT_DeleteLookDevLightOperator,
    SIMPLE_OT_import_usd,
    SF_CleanupOrphansCombined2,
    SF_ReloadAllImages,
    ReloadTextureOperator,
    SF_OT_BuildSceneOperator,
    OBJECT_OT_SetVertexColor,
    OBJECT_OT_ApplySkinColor,
    OBJECT_OT_ApplyAllGeometryNodesSettings,
    ChangeTextureNodeColorSpaceOperator,
    SF_OT_AddPropertiesAndLink,
    SF_OT_LoadAndLinkNodeGroup,
    SF_OT_CreateCharacterLights,
    SF_OT_LinkCharacterLights,
    SF_OT_LinkRimToNode,
    SubdivideClass1,
    SF_ImportUSDOperator,
    SF_OT_RefreshDrivers,
    SF_MaterialSwitcherProperties,
    SF_OT_SwitchLookdevMaterial,
    SF_ReplaceAssetOperator,
    SF_OT_ParentLightToTurntable,
    SF_OT_ApplyLookdevMaterial,
    SF_OT_PopupWarning,
    SF_OT_ConvertToPaintShader,
    SF_OT_CleanupMaterialNodes,
    LDV_OT_OpenEmptyFile,
    SF_OT_SetLayerOperator,
    SF_OT_ImportSelectedLightPreset,
    SF_OT_DeleteLightPresetCollection,
    SF_OT_OpenAssetFolder,
    SF_OT_SaveLightPreset,
    SF_OT_OpenLightPresetPrompt,
    SFPaintPresetProperties,
    SF_OT_SaveSFPaintPresetPopup,
    SF_OT_AssignSFPaintPreset,
    LDV_OT_AutoImportPopup,
    SF_OT_AutoImportShader,
    SF_OT_ConvertPrincipledToSFPaint,
    LDV_OT_AppendPublishedAsset,
    SF_OT_SetCharacterLightAndOutline,
    SF_OT_LoadAndLinkNodeGroupC,
    OBJECT_OT_ConvertVGroupToColorC,
    SF_OT_LineMode,
    SF_OT_ColorMode,
    SF_OT_LineDefaultSettings,
    SF_OT_LineDefaultSettingsApply,
    DEV_OT_reload_blendldv,
    DEV_OT_deploy_blendldv,
    FUZZ_OT_TransferFreestyleEdges,
    # 패널
    SF_PT_LookDev2Panel
]


def register():
    global thumb_previews
    thumb_previews = previews.new()

    init_browser_state_file()
    for project_key in PROJECTS.keys():
        try:
            update_asset_list_cache(project_key)
        except Exception as e:
            print(f"[LDV WARN] asset cache init failed for {project_key}: {e}")

    # 모든 클래스 등록
    for cls in classes:
        bpy.utils.register_class(cls)
    register_props()
    # Scene 프로퍼티 등록
    bpy.types.Scene.ldv_browser_tool = bpy.props.PointerProperty(type=LdvBrowserProperties)
    bpy.types.Scene.sf_mat_switcher = bpy.props.PointerProperty(type=SF_MaterialSwitcherProperties)
    bpy.types.Scene.sf_paint_presets = bpy.props.PointerProperty(type=SFPaintPresetProperties)

    bpy.types.Scene.outline_target_mode = bpy.props.EnumProperty(
        name="Outline Target",
        items=[
            ('ALL', "All", "Apply to all geo meshes"),
            ('SELECTED', "Selected", "Apply only to selected meshes"),
        ],
        default='ALL'
    )
    bpy.types.Scene.manual_import_enabled = bpy.props.BoolProperty(
        name="Manual",
        description="Check to show manual import buttons",
        default=False
    )
    bpy.types.Scene.layer_name_input = bpy.props.StringProperty(
        name="SubCollection",
        description="Enter name for new layer (e.g. cloth)",
        default=""
    )
    bpy.types.Scene.light_preset_choice = bpy.props.EnumProperty(
        name="Light Preset",
        items=get_light_presets
    )

    # 타이머 등록: 상태 복원
    def load_browser_state_timer():
        tool = bpy.context.scene.ldv_browser_tool
        if not sync_browser_state_to_current_file(tool, bpy.data.filepath, save_state=True):
            load_browser_state(tool)
        return None

    bpy.app.timers.register(load_browser_state_timer)
    
    if make_paths_absolute not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(make_paths_absolute)
    if load_scene_post_handler not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(load_scene_post_handler)


def unregister():
    global thumb_previews

    # 안전하게 Scene 프로퍼티 제거
    for prop in [
        "ldv_browser_tool",
        "sf_mat_switcher",
        "outline_target_mode",
        "manual_import_enabled",
        "layer_name_input",
        "light_preset_choice",
        "sf_paint_presets"
    ]:
        if hasattr(bpy.types.Scene, prop):
            try:
                delattr(bpy.types.Scene, prop)
            except Exception as e:
                print(f"[WARN] Failed to delete bpy.types.Scene.{prop}: {e}")

    # 클래스 등록 해제 (역순)
    for cls in reversed(classes):
        try:
            if hasattr(cls, "bl_rna"):
                bpy.utils.unregister_class(cls)
        except Exception as e:
            print(f"[INFO] unregister 실패 또는 이미 해제됨: {e}")
    del bpy.types.Scene.sf_render_mode
    # 썸네일 프리뷰 제거
    if thumb_previews:
        previews.remove(thumb_previews)
        thumb_previews = None
        
    if make_paths_absolute in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(make_paths_absolute)
    if load_scene_post_handler in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(load_scene_post_handler)

    
if __name__ == "__main__":
    try:
        unregister()
    except Exception as e:
        print(f"[INFO] unregister 실패 또는 이미 해제됨: {e}")

    try:
        register()
        print("[INFO] register 성공적으로 완료됨 ✅")
    except Exception as e:
        print(f"[ERROR] register 실패: {e}")

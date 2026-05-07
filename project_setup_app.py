import argparse
import os
import tkinter as tk
from tkinter import messagebox, ttk

from pipeline_shared import (
    get_project_entry,
    get_project_names,
    load_pipeline_config,
    normalize_project_name,
    save_pipeline_config,
    sync_legacy_rrrender_paths_json,
)


FIELD_SPECS = [
    ("identity.project_prefix", "Prefix"),
    ("identity.profile", "Profile"),
    ("paths.project_root", "Project Root"),
    ("paths.asset_root", "Asset Root"),
    ("paths.scene_root", "Scene Root"),
    ("paths.json_root", "Json Root"),
    ("paths.output_root", "Output Root"),
    ("paths.cache_root", "Cache Root"),
    ("paths.render_preset_json", "Render Preset JSON"),
    ("paths.render_setting_json", "Render Setting JSON"),
    ("scene_structure.scene_depth", "Depth Count"),
    ("scene_structure.work_folder_name", "Work Folder"),
    ("scene_browser.levels[0].label", "Depth 0 Name"),
    ("scene_browser.levels[0].root_path", "Depth 0 Root"),
    ("scene_browser.levels[0].path_mode", "Depth 0 Mode"),
    ("scene_browser.levels[1].label", "Depth 1 Name"),
    ("scene_browser.levels[1].fixed_options[0]", "Depth 1 Folder"),
    ("scene_browser.levels[1].path_mode", "Depth 1 Mode"),
    ("scene_browser.levels[2].label", "Depth 2 Name"),
    ("scene_browser.levels[2].default", "Depth 2 Default"),
    ("scene_browser.levels[2].path_mode", "Depth 2 Mode"),
    ("scene_browser.file_level_id", "File Level"),
    ("scene_structure.identifier_source", "Identifier Source"),
    ("scene_structure.scene_level_id", "Scene Level ID"),
    ("scene_structure.cut_level_id", "Cut Level ID"),
    ("scene_structure.work_level_id", "Work Level ID"),
    ("scene_structure.cache_path_mode", "Cache Path Mode"),
    ("scene_structure.cache_relative_path", "Cache Relative Path"),
    ("scene_filename_rules.example", "Filename Example"),
    ("scene_filename_rules.scene_token_pattern", "Scene Token Pattern"),
    ("scene_filename_rules.cut_token_pattern", "Cut Token Pattern"),
    ("scene_filename_rules.version_pattern", "Version Pattern"),
    ("dcc.maya.work_dirs[0]", "Maya Work Dir"),
    ("cache.root_mode", "Cache Root Mode"),
    ("cache.root_template", "Cache Root Template"),
    ("output.root_template", "Output Root Template"),
]


def _get_nested(data, dotted_key, default=""):
    current = data
    parts = []
    for chunk in dotted_key.split("."):
        while chunk:
            if "[" in chunk and chunk.endswith("]"):
                before, after = chunk.split("[", 1)
                if before:
                    parts.append(before)
                index = after[:-1]
                parts.append(int(index))
                chunk = ""
            else:
                parts.append(chunk)
                chunk = ""
    for part in parts:
        if isinstance(part, int):
            if not isinstance(current, list) or part >= len(current):
                return default
            current = current[part]
        else:
            if not isinstance(current, dict):
                return default
            current = current.get(part)
    if current is None:
        return default
    if isinstance(current, list):
        return ", ".join(str(item) for item in current)
    return str(current)


def _set_nested(data, dotted_key, value):
    current = data
    parts = []
    for chunk in dotted_key.split("."):
        while chunk:
            if "[" in chunk and chunk.endswith("]"):
                before, after = chunk.split("[", 1)
                if before:
                    parts.append(before)
                parts.append(int(after[:-1]))
                chunk = ""
            else:
                parts.append(chunk)
                chunk = ""

    for idx, part in enumerate(parts[:-1]):
        next_part = parts[idx + 1]
        if isinstance(part, int):
            while len(current) <= part:
                current.append({} if not isinstance(next_part, int) else [])
            if current[part] is None:
                current[part] = {} if not isinstance(next_part, int) else []
            current = current[part]
            continue

        child = current.get(part)
        if isinstance(next_part, int):
            if not isinstance(child, list):
                child = []
                current[part] = child
        else:
            if not isinstance(child, dict):
                child = {}
                current[part] = child
        current = child

    last = parts[-1]
    if isinstance(last, int):
        while len(current) <= last:
            current.append(None)
        current[last] = value
    else:
        current[last] = value


class ProjectSetupApp:
    def __init__(self, root, initial_project="", tool_name=""):
        self.root = root
        self.tool_name = tool_name
        self.payload = load_pipeline_config()
        self.project_names = get_project_names(self.payload)
        self.current_project = normalize_project_name(initial_project, self.payload)
        if self.current_project not in self.project_names and self.project_names:
            self.current_project = self.project_names[0]

        self.project_var = tk.StringVar(value=self.current_project)
        self.status_var = tk.StringVar(value="Ready")
        self.field_vars = dict((field_key, tk.StringVar()) for field_key, _label in FIELD_SPECS)

        self._build_ui()
        if self.current_project:
            self._load_project(self.current_project)

    def _build_ui(self):
        title = "Project Setup App"
        if self.tool_name:
            title += f" - {self.tool_name}"
        self.root.title(title)
        self.root.geometry("980x560")
        self.root.minsize(840, 500)

        wrapper = ttk.Frame(self.root, padding=12)
        wrapper.pack(fill="both", expand=True)
        wrapper.columnconfigure(1, weight=1)
        wrapper.rowconfigure(0, weight=1)

        left = ttk.Frame(wrapper)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 12))

        ttk.Label(left, text="Projects").pack(anchor="w")
        self.project_listbox = tk.Listbox(left, exportselection=False, width=24, height=24)
        self.project_listbox.pack(fill="y", expand=False)
        for project_name in self.project_names:
            self.project_listbox.insert("end", project_name)
        self.project_listbox.bind("<<ListboxSelect>>", self._on_project_select)
        if self.current_project in self.project_names:
            index = self.project_names.index(self.current_project)
            self.project_listbox.selection_set(index)
            self.project_listbox.see(index)

        right = ttk.Frame(wrapper)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(1, weight=1)

        header = ttk.Frame(right)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        header.columnconfigure(1, weight=1)

        ttk.Label(header, text="Current Project").grid(row=0, column=0, sticky="w")
        ttk.Label(header, textvariable=self.project_var).grid(row=0, column=1, sticky="w")

        for row_index, (field_key, label) in enumerate(FIELD_SPECS, start=1):
            ttk.Label(right, text=label).grid(row=row_index, column=0, sticky="w", pady=4)
            entry = ttk.Entry(right, textvariable=self.field_vars[field_key])
            entry.grid(row=row_index, column=1, sticky="ew", pady=4)

        button_row = ttk.Frame(right)
        button_row.grid(row=len(FIELD_SPECS) + 1, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        ttk.Button(button_row, text="Reload", command=self.reload).pack(side="left")
        ttk.Button(button_row, text="Save Project", command=self.save_current_project).pack(side="left", padx=6)
        ttk.Button(button_row, text="Save + Close", command=self.save_and_close).pack(side="left")

        status = ttk.Label(right, textvariable=self.status_var)
        status.grid(row=len(FIELD_SPECS) + 2, column=0, columnspan=2, sticky="w", pady=(10, 0))

    def _on_project_select(self, _event=None):
        selection = self.project_listbox.curselection()
        if not selection:
            return
        self._load_project(self.project_listbox.get(selection[0]))

    def _load_project(self, project_name):
        project = get_project_entry(project_name, self.payload) or {}
        self.current_project = project_name
        self.project_var.set(project_name)
        for field_key, _label in FIELD_SPECS:
            self.field_vars[field_key].set(_get_nested(project, field_key, ""))
        self.status_var.set(f"Loaded {project_name}")

    def reload(self):
        self.payload = load_pipeline_config()
        self.project_names = get_project_names(self.payload)
        if self.current_project not in self.project_names and self.project_names:
            self.current_project = self.project_names[0]
        self._load_project(self.current_project)

    def save_current_project(self):
        if not self.current_project:
            messagebox.showwarning("Project Setup", "No project selected.")
            return

        project = get_project_entry(self.current_project, self.payload) or {}
        for field_key, _label in FIELD_SPECS:
            _set_nested(project, field_key, self.field_vars[field_key].get().strip())
        self.payload.setdefault("projects", {})[self.current_project] = project
        save_pipeline_config(self.payload)
        sync_legacy_rrrender_paths_json(self.payload)
        self.status_var.set(f"Saved {self.current_project} and synced legacy project paths")

    def save_and_close(self):
        self.save_current_project()
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tool", default="", help="Tool name opening the setup app")
    parser.add_argument("--project", default="", help="Initially selected project")
    args = parser.parse_args()

    root = tk.Tk()
    app = ProjectSetupApp(root, initial_project=args.project, tool_name=args.tool)
    root.mainloop()


if __name__ == "__main__":
    main()

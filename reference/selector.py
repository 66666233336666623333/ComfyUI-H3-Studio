"""Load enabled reference files from one saved selection, using native loaders."""

import json
from pathlib import Path, PureWindowsPath

import folder_paths
from nodes import LoadImage
from comfy_api.latest import io
from comfy_extras.nodes_audio import LoadAudio
from comfy_extras.nodes_video import LoadVideo

from .validation import PORTS


EXTENSIONS = {
    "image": {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".avif", ".gif", ".apng"},
    "audio": {".wav", ".mp3", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".aif", ".aiff", ".wma"},
    "video": {".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v", ".mpeg", ".mpg"},
}
EMPTY_SELECTION = '{"image":[],"audio":[],"video":[]}'


def parse_selection(manifest):
    try:
        selection = json.loads(manifest)
    except (json.JSONDecodeError, TypeError) as error:
        raise ValueError("参考清单格式无效，请打开管理参考面板检查。") from error
    if not isinstance(selection, dict) or set(selection) - set(PORTS):
        raise ValueError("参考清单只支持 image、audio、video 三组。")
    result = {}
    enabled_count = 0
    for kind, maximum in PORTS.items():
        entries = selection.get(kind, [])
        if not isinstance(entries, list) or len(entries) > maximum:
            raise ValueError(f"{kind} 最多保留 {maximum} 个参考位置。")
        result[kind] = []
        for index, entry in enumerate(entries):
            if entry is None:
                result[kind].append(None)
                continue
            if (not isinstance(entry, dict) or set(entry) - {"path", "enabled"}
                    or not isinstance(entry.get("path"), str)
                    or not isinstance(entry.get("enabled", True), bool)):
                raise ValueError(f"{kind}_{index + 1} 的文件或启用状态无效。")
            if entry.get("enabled", True):
                if not entry["path"]:
                    raise ValueError(f"{kind}_{index + 1} 已启用，但没有选择文件。")
                enabled_count += 1
            result[kind].append({"path": entry["path"], "enabled": entry.get("enabled", True)})
        result[kind].extend([None] * (maximum - len(entries)))
    if enabled_count > 12:
        raise ValueError(f"当前启用 {enabled_count} 个参考文件，最多 12 个；请取消勾选不需要的参考。")
    return result


def input_file(path, kind):
    relative = path.replace("\\", "/")
    if (not relative or relative.startswith("/") or ":" in relative
            or PureWindowsPath(path).drive or ".." in relative.split("/")):
        raise ValueError("参考文件只能选择 ComfyUI input 目录内的相对路径。")
    root = Path(folder_paths.get_input_directory()).resolve()
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError(f"参考文件不存在或位于 input 目录之外：{path!r}")
    if resolved.suffix.lower() not in EXTENSIONS[kind]:
        raise ValueError(f"{path!r} 不是该 {kind} 参考口支持的文件类型。")
    return resolved


class H3StudioReferenceLoader(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        outputs = []
        for kind, maximum in PORTS.items():
            output_type = {"image": io.Image, "audio": io.Audio, "video": io.Video}[kind]
            outputs.extend(output_type.Output(display_name=f"{kind}_{i}") for i in range(1, maximum + 1))
        outputs.extend([io.Boolean.Output(display_name="use_video_audio"),
                        io.String.Output(display_name="selection_report")])
        return io.Schema(
            node_id="H3StudioReferenceLoader",
            display_name="H3 · Reference loader (internal)",
            category="MiniMax H3 / Studio / internal",
            search_aliases=["H3 selector", "批量加载参考", "参考素材选择"],
            description="批量选择参考素材，勾选本次使用的图像/音频/视频。未启用的位置不读取文件，输出为空。use_video_audio 输出连接 H3 多参考校验节点。",
            inputs=[io.String.Input("manifest", default=EMPTY_SELECTION, multiline=True,
                                    dynamic_prompts=False, socketless=True),
                    io.Boolean.Input("use_video_audio", default=True)],
            outputs=outputs,
        )

    @classmethod
    def validate_inputs(cls, manifest):
        try:
            selection = parse_selection(manifest)
            for kind, entries in selection.items():
                for entry in entries:
                    if entry and entry["enabled"]:
                        input_file(entry["path"], kind)
        except ValueError as error:
            return str(error)
        return True

    @classmethod
    def fingerprint_inputs(cls, manifest, use_video_audio):
        selection = parse_selection(manifest)
        files = []
        for kind, entries in selection.items():
            for entry in entries:
                if entry and entry["enabled"]:
                    path = input_file(entry["path"], kind)
                    stat = path.stat()
                    files.append((str(path), stat.st_size, stat.st_mtime_ns))
        return manifest, use_video_audio, files

    @classmethod
    def execute(cls, manifest, use_video_audio):
        selection = parse_selection(manifest)
        values, selected = [], []
        for kind, entries in selection.items():
            for index, entry in enumerate(entries, 1):
                value = None
                if entry and entry["enabled"]:
                    path = input_file(entry["path"], kind)
                    annotated = f"{path} [input]"
                    if kind == "image":
                        value = LoadImage().load_image(annotated)[0]
                        if value.shape[0] != 1:
                            raise ValueError(f"image_{index} 包含多帧，请选择静态图片。")
                    elif kind == "audio":
                        value = LoadAudio.execute(audio=annotated)[0]
                    else:
                        value = LoadVideo.execute(file=annotated)[0]
                    selected.append({"port": f"{kind}_{index}", "file": entry["path"]})
                values.append(value)
        report = json.dumps({"enabled_files": len(selected), "selected": selected,
                             "use_video_audio": use_video_audio}, ensure_ascii=False, indent=2)
        return io.NodeOutput(*values, use_video_audio, report)

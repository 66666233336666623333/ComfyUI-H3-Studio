"""Local text, duration and output-path rules; no model imports."""
import codecs
import math
from pathlib import Path

TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".text", ".rst", ".log", ".json", ".yaml", ".yml", ".csv", ".srt"}
ENCODINGS = ["自动", "utf-8", "utf-8-sig", "ascii", "utf-16", "utf-16-le", "utf-16-be", "utf-32", "utf-32-le", "utf-32-be", "gb2312", "gbk", "gb18030"]
PRESETS = {
    "横屏 16:9 · 1344×768": (1344, 768),
    "横屏 16:9 · 1152×640": (1152, 640),
    "横屏 16:9 · 960×544": (960, 544),
    "横屏 16:9 · 736×416": (736, 416),
    "竖屏 9:16 · 768×1344": (768, 1344),
    "竖屏 9:16 · 640×1152": (640, 1152),
    "竖屏 9:16 · 544×960": (544, 960),
    "方形 1:1 · 1024×1024": (1024, 1024),
    "方形 1:1 · 768×768": (768, 768),
    "横屏 4:3 · 1152×864": (1152, 864),
    "竖屏 3:4 · 864×1152": (864, 1152),
}
MAX_TEXT_BYTES = 4 * 1024 * 1024

def duration_frames(seconds):
    target = max(5, round(float(seconds) * 24))
    padded = target + (5 - target % 17) % 17
    return target, padded

def decode_text(data, encoding="自动"):
    if len(data) > MAX_TEXT_BYTES:
        raise ValueError("提示词文件不能超过 4 MiB。")
    if encoding not in ENCODINGS:
        raise ValueError("不支持该编码，请从编码列表选择。")
    used = encoding
    if encoding == "自动":
        for bom, name in [(codecs.BOM_UTF32_LE, "utf-32"), (codecs.BOM_UTF32_BE, "utf-32"),
                          (codecs.BOM_UTF8, "utf-8-sig"), (codecs.BOM_UTF16_LE, "utf-16"),
                          (codecs.BOM_UTF16_BE, "utf-16")]:
            if data.startswith(bom):
                used = name
                break
        else:
            if b"\0" in data:
                raise ValueError("文件含零字节；无 BOM 的 UTF-16/32 请手动选择准确编码。")
            try:
                data.decode("utf-8", errors="strict")
                used = "ascii" if data.isascii() else "utf-8"
            except UnicodeDecodeError:
                used = "gb18030"
    try:
        text = data.decode(used, errors="strict").lstrip("\ufeff")
    except UnicodeError as exc:
        raise ValueError(f"文件不能按 {used} 严格解码，请更换编码；没有替换或丢弃字符。") from exc
    if "\0" in text:
        raise ValueError("解码结果含零字符，请检查文件或手动指定编码。")
    return text, used

def input_text_path(root, filename):
    root = Path(root).resolve()
    rel = Path(filename)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError("提示词文件必须位于 ComfyUI input 文件夹内。")
    path = (root / rel).resolve()
    if not path.is_relative_to(root) or path.suffix.lower() not in TEXT_EXTENSIONS or not path.is_file():
        raise ValueError(f"提示词文件不存在、格式不支持或超出 input 目录：{filename}")
    return path

def resolve_output_dir(default, selected):
    root = Path(default).resolve()
    text = selected.strip().strip('"')
    if not text:
        return root
    path = Path(text)
    if not path.is_absolute():
        path = (root / path).resolve()
        if not path.is_relative_to(root):
            raise ValueError("相对输出路径必须位于 ComfyUI output 内；其他位置请填写绝对路径。")
    return path.resolve()

def safe_prefix(value):
    text = value.strip()
    if not text or any(c in text for c in '<>:"/\\|?*') or text in (".", "..") or text.endswith((".", " ")):
        raise ValueError("文件名前缀不能为空，也不能包含路径或 Windows 文件名保留字符。")
    if text.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *("COM"+str(i) for i in range(1,10)), *("LPT"+str(i) for i in range(1,10))}:
        raise ValueError("文件名前缀不能使用 Windows 设备保留名称。")
    return text

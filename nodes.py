import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path

import folder_paths
from comfy_api.latest import io, ui
from comfy_api.latest import Types
from comfy.cli_args import args

from .core import ENCODINGS, PRESETS, decode_text, duration_frames, input_text_path, resolve_output_dir, safe_prefix
from .pipeline import TEMPLATES, build_pipeline
from .reference.selector import H3StudioReferenceLoader

CATEGORY = "MiniMax H3 / Studio"
References = io.Custom("H3_STUDIO_REFERENCES")
Control = io.Custom("H3_STUDIO_CONTROL")
SOURCES = ["手写提示词", "文本文件", "文件 + 手写补充"]

def choices(folder, default):
    names = folder_paths.get_filename_list(folder)
    return names if default in names else [default, *names]

def default(old_id, name):
    return TEMPLATES[str(old_id)]["inputs"][name]

class H3StudioPrompt(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="H3StudioPrompt", display_name="H3 · 提示词工作台", category=CATEGORY,
            inputs=[
                io.Combo.Input("source", display_name="提示词来源", options=SOURCES, default=SOURCES[0]),
                io.String.Input("text_file", display_name="已选文本文件", default="", tooltip="点击选择文本文件；文件保存在 input/h3_studio_prompts。"),
                io.Combo.Input("encoding", display_name="文件编码", options=ENCODINGS, default="自动"),
                io.String.Input("prompt", display_name="手写提示词 / 补充", default="", multiline=True, dynamic_prompts=False),
            ], outputs=[io.String.Output("prompt", display_name="提示词")], has_intermediate_output=True)

    @classmethod
    def fingerprint_inputs(cls, source, text_file, encoding, prompt):
        if source == SOURCES[0]:
            return source, prompt
        path = input_text_path(folder_paths.get_input_directory(), text_file)
        return source, hashlib.sha256(path.read_bytes()).hexdigest(), encoding, prompt

    @classmethod
    def validate_inputs(cls, source, text_file, encoding):
        if source == SOURCES[0]:
            return True
        try:
            path = input_text_path(folder_paths.get_input_directory(), text_file)
            decode_text(path.read_bytes(), encoding)
        except ValueError as error:
            return str(error)
        return True

    @classmethod
    def execute(cls, source, text_file, encoding, prompt):
        if source == SOURCES[0]:
            return io.NodeOutput(prompt, ui={"studio_status": ["使用手写提示词"]})
        path = input_text_path(folder_paths.get_input_directory(), text_file)
        text, used = decode_text(path.read_bytes(), encoding)
        if source == SOURCES[2] and prompt:
            text = text.rstrip() + "\n\n" + prompt
        return io.NodeOutput(text, ui={"studio_status": [f"{path.name} · {used} · {len(text)} 字符"]})

class H3StudioReferences(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="H3StudioReferences", display_name="H3 · 参考选通器", category=CATEGORY,
            inputs=[io.String.Input("manifest", default='{"image":[],"audio":[],"video":[]}', multiline=True, socketless=True),
                    io.Boolean.Input("use_video_audio", default=False)],
            outputs=[References.Output("references", display_name="全部参考")])

    @classmethod
    def validate_inputs(cls, manifest):
        return H3StudioReferenceLoader.validate_inputs(manifest)

    @classmethod
    def execute(cls, manifest, use_video_audio):
        return io.NodeOutput({"manifest":manifest, "use_video_audio":use_video_audio})

class H3StudioControlVideo(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        files = ["（不使用）"] + sorted(folder_paths.filter_files_content_types(
            [f for f in os.listdir(folder_paths.get_input_directory())
             if (Path(folder_paths.get_input_directory()) / f).is_file()], ["video"]))
        return io.Schema(node_id="H3StudioControlVideo", display_name="H3 · FunControl 输入视频", category=CATEGORY,
            inputs=[
                io.Combo.Input("file", display_name="控制视频", options=files, default="（不使用）"),
                io.Float.Input("start_time", display_name="起始秒数", default=0, min=0, max=86400, step=0.1),
                io.Float.Input("duration", display_name="截取秒数（0 = 全部）", default=0, min=0, max=86400, step=0.1),
            ], outputs=[Control.Output("control", display_name="控制素材")])

    @classmethod
    def execute(cls, file, start_time, duration):
        return io.NodeOutput({"file": "" if file=="（不使用）" else file,
                              "start_time":start_time, "duration":duration})

class H3StudioEngine(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        model = default(1, "unet_name")
        fast = default(768, "unet_name")
        def model_input(name, folder, value, label, advanced=False):
            return io.Combo.Input(name, display_name=label, options=choices(folder,value), default=value, advanced=advanced)
        return io.Schema(node_id="H3StudioEngine", display_name="H3 · 一体化生成控制台", category=CATEGORY,
            enable_expand=True,
            inputs=[
                io.String.Input("prompt", display_name="提示词", force_input=True),
                References.Input("references", display_name="参考素材"),
                Control.Input("control", display_name="FunControl 输入", optional=True),
                io.Combo.Input("resolution", display_name="预设分辨率", options=list(PRESETS), default=list(PRESETS)[0]),
                io.Int.Input("duration_seconds", display_name="目标时长（秒）", default=12, min=3, max=15, step=1,
                             tooltip="沿用 MiniMax H3 的 17k+5 帧分档；12 秒对应 294 帧 / 12.25 秒。"),
                io.Boolean.Input("enable_fasth3", display_name="FastH3", default=True),
                io.Boolean.Input("enable_lora", display_name="加速 LoRA", default=False),
                io.Boolean.Input("enable_funcontrol", display_name="FunControl", default=False),
                model_input("minimax_model","diffusion_models",model,"MiniMax H3 模型"),
                model_input("fasth3_model","diffusion_models",fast,"FastH3 模型"),
                model_input("lora_name","loras",default(2,"lora_name"),"加速 LoRA 文件"),
                io.Float.Input("lora_strength", display_name="LoRA 强度", default=1, min=0, max=10, step=.05),
                io.Float.Input("funcontrol_strength", display_name="FunControl 强度", default=1, min=0, max=10, step=.05),
                io.Int.Input("seed", display_name="随机种子", default=0, min=0, max=0xffffffffffffffff, control_after_generate=True),
                io.Int.Input("normal_steps",display_name="常规步数",default=20,min=1,max=100,advanced=True),
                io.Int.Input("lora_steps",display_name="LoRA 步数",default=8,min=1,max=100,advanced=True),
                io.Int.Input("fast_steps",display_name="FastH3 步数",default=8,min=1,max=100,advanced=True),
                model_input("funcontrol_model","model_patches",default(752,"name"),"FunControl 模型",True),
                model_input("clip_name","text_encoders",default(35,"clip_name"),"文本编码器",True),
                model_input("video_vae","vae",default(33,"vae_name"),"视频 VAE",True),
                model_input("audio_vae","vae",default(34,"vae_name"),"音频 VAE",True),
                model_input("detector_model","diffusion_models",default(748,"unet_name"),"人体检测模型",True),
                model_input("pose_model","checkpoints",default(747,"ckpt_name"),"姿态模型",True),
            ],
            outputs=[io.Video.Output("video", display_name="成片"),
                     io.Image.Output("pose", display_name="FunControl 姿态")])

    @classmethod
    def execute(cls, prompt, references, control=None, **options):
        duration_frames(options["duration_seconds"])
        if options["enable_funcontrol"] and not options["enable_fasth3"]:
            file = (control or {}).get("file")
            if not file:
                raise ValueError("FunControl 已开启，请在输入视频面板选择素材。")
            path = Path(folder_paths.get_annotated_filepath(file)).resolve()
            if not path.is_relative_to(Path(folder_paths.get_input_directory()).resolve()) or not path.is_file():
                raise ValueError("控制视频不存在或不在 ComfyUI input 目录中。")
        graph, outputs = build_pipeline(options,prompt,references,control)
        return io.NodeOutput(*outputs, expand=graph)

class H3StudioSaveVideo(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="H3StudioSaveVideo", display_name="H3 · 保存与成片预览", category=CATEGORY,
            is_output_node=True, hidden=[io.Hidden.prompt,io.Hidden.extra_pnginfo],
            inputs=[
                io.Video.Input("video", display_name="成片"),
                io.String.Input("output_directory",display_name="输出目录（留空 = 官方 output）", default="",
                    tooltip="可填写绝对路径；相对路径位于 ComfyUI output 下。不改变全局输出目录。"),
                io.String.Input("filename_prefix",display_name="文件名前缀",default="H3_Studio"),
                io.Combo.Input("format",display_name="格式",options=["mp4","mkv","webm"],default="mp4"),
                io.Combo.Input("codec",display_name="编码器",options=["auto","h264","av1"],default="auto"),
            ],outputs=[io.Video.Output("video"),io.String.Output("saved_path",display_name="保存位置")])

    @classmethod
    def validate_inputs(cls, output_directory, filename_prefix, format, codec):
        try:
            resolve_output_dir(folder_paths.get_output_directory(),output_directory)
            safe_prefix(filename_prefix)
            if format=="webm" and codec=="h264":
                return "WebM 不支持 H.264，请选择 AV1 或改用 MP4。"
        except (ValueError,OSError) as error:
            return str(error)
        return True

    @classmethod
    def execute(cls, video, output_directory, filename_prefix, format, codec):
        directory=resolve_output_dir(folder_paths.get_output_directory(),output_directory)
        filename_prefix=safe_prefix(filename_prefix)
        directory.mkdir(parents=True,exist_ok=True)
        width,height=video.get_dimensions()
        full,filename,counter,_,_=folder_paths.get_save_image_path(filename_prefix,str(directory),width,height)
        path=Path(full)/f"{filename}_{counter:05}_.{format}"
        metadata={}
        if not args.disable_metadata:
            if cls.hidden.extra_pnginfo:metadata.update(cls.hidden.extra_pnginfo)
            if cls.hidden.prompt:metadata["prompt"]=cls.hidden.prompt
        actual_codec = "av1" if format=="webm" and codec=="auto" else codec
        video.save_to(str(path),format=Types.VideoContainer(format),codec=Types.VideoCodec(actual_codec),
                      metadata=metadata or None)
        output_root=Path(folder_paths.get_output_directory()).resolve()
        if path.resolve().is_relative_to(output_root):
            rel=path.resolve().relative_to(output_root)
            preview=ui.SavedResult(rel.name,rel.parent.as_posix() if rel.parent!=Path(".") else "",io.FolderType.output)
        else:
            temp=Path(folder_paths.get_temp_directory())/"h3_studio_previews"
            temp.mkdir(parents=True,exist_ok=True)
            preview_path=temp/f"{uuid.uuid4().hex}.{format}"
            try:
                os.link(path,preview_path)
            except OSError:
                shutil.copyfile(path,preview_path)
            preview=ui.SavedResult(preview_path.name,"h3_studio_previews",io.FolderType.temp)
        data=ui.PreviewVideo([preview]).as_dict()
        data["studio_status"]=[str(path)]
        return io.NodeOutput(video,str(path),ui=data)

STUDIO_NODES=[H3StudioPrompt,H3StudioReferences,H3StudioControlVideo,H3StudioEngine,H3StudioSaveVideo]

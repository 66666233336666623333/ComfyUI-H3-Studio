# SPDX-License-Identifier: GPL-3.0-only
# Derived from ComfyUI comfy_extras/nodes_minimax_h3.py (ComfyUI contributors).
# Modified for multi-reference selection, validation and duration-preserving video input.
# See THIRD_PARTY_NOTICES.md and LICENSES/GPL-3.0.txt.
import json
import math
from fractions import Fraction

import node_helpers
import nodes
from comfy_api.latest import io, ui
from comfy_extras import nodes_minimax_h3 as h3

from .validation import PORTS, audio_duration, validate_combined_audio, validate_references


MISSING = object()


def resample_reference_frames(frames, source_fps, duration):
    """Keep playback time: sample/drop/repeat frames, then pad only the tail."""
    source_fps = Fraction(source_fps)
    frame_count = math.ceil(duration * h3.FPS)
    indices = [min((i * source_fps.numerator) // (h3.FPS * source_fps.denominator),
                   frames.shape[0] - 1) for i in range(frame_count)]
    padded_count = h3.align_frame_count(frame_count)
    indices.extend([indices[-1]] * (padded_count - frame_count))
    return frames[indices], frame_count, padded_count - frame_count


class H3StudioReferenceConditioning(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        inputs = [
            io.Clip.Input("clip", lazy=True),
            io.Vae.Input("vae", optional=True, lazy=True,
                         tooltip="有图像或视频参考时必须连接 H3 视频 VAE。"),
            io.Vae.Input("audio_vae", optional=True, lazy=True,
                         tooltip="有独立音频或启用的视频音轨时必须连接 H3 音频 VAE。"),
            io.String.Input("prompt", default="", multiline=True, dynamic_prompts=True),
            io.Int.Input("width", default=1344, min=32, max=nodes.MAX_RESOLUTION, step=32),
            io.Int.Input("height", default=768, min=32, max=nodes.MAX_RESOLUTION, step=32),
            io.Int.Input("length", default=124, min=5, max=3600, step=17,
                         tooltip="生成帧数，沿用 H3 的 24 fps / 17k+5 网格；不限制参考视频长度。"),
            io.Combo.Input("ref_image_size", options=["match", "max"], default="match"),
            io.Boolean.Input("use_video_audio", default=True,
                             tooltip="保留视频音轨，与独立音频合计最多 3 段、15 秒；超限报错。音轨不另占混合文件数。"),
        ]
        for kind, maximum in PORTS.items():
            input_type = {"image": io.Image, "audio": io.Audio, "video": io.Video}[kind]
            for index in range(1, maximum + 1):
                inputs.append(input_type.Input(f"{kind}_{index}", optional=True))
        return io.Schema(
            node_id="H3StudioReferenceConditioning",
            display_name="H3 · Reference conditioning (internal)",
            category="MiniMax H3 / Studio / internal",
            description="9 图 / 3 音频口 / 3 视频口；混合最多 12 文件。启用的视频音轨与独立音频合计最多 3 段、15 秒。视频合计 ≤15 秒，每段素材 2–15 秒。超限直接报错。",
            inputs=inputs,
            outputs=[io.Conditioning.Output(display_name="positive"),
                     io.Latent.Output(), io.String.Output(display_name="validation_report")],
            has_intermediate_output=True,
        )

    @classmethod
    def check_lazy_status(cls, clip=None, vae=MISSING, audio_vae=MISSING, **kwargs):
        groups, durations, _ = validate_references(kwargs)
        # Inspect soundtracks before requesting any unresolved model inputs.
        if (kwargs.get("use_video_audio", True) and groups["video"]
                and any(model is None for model in (clip, vae, audio_vae))):
            tracks = []
            for port, video in groups["video"]:
                soundtrack = video.get_components().audio
                if soundtrack is not None:
                    tracks.append((port + ".audio", audio_duration(soundtrack, port + ".audio")))
            validate_combined_audio(tracks + durations["audio"])
            if tracks and audio_vae is MISSING:
                raise ValueError("启用的视频音轨需要 audio_vae（H3 音频 VAE）。")
        if (groups["image"] or groups["video"]) and vae is MISSING:
            raise ValueError("有图像或视频参考时，请连接 vae（H3 视频 VAE）。")
        if groups["audio"] and audio_vae is MISSING:
            raise ValueError("有音频参考时，请连接 audio_vae（H3 音频 VAE）。")
        needed = ["clip"] if clip is None else []
        if (groups["image"] or groups["video"]) and vae is None:
            needed.append("vae")
        if audio_vae is None and (groups["audio"] or (groups["video"] and kwargs.get("use_video_audio", True))):
            needed.append("audio_vae")
        return needed

    @classmethod
    def execute(cls, clip, prompt, width, height, length, ref_image_size="match",
                use_video_audio=True, vae=MISSING, audio_vae=MISSING, **kwargs):
        groups, durations, report = validate_references(kwargs)
        if groups["image"] or groups["video"]:
            if vae is MISSING or vae is None:
                raise ValueError("图像或视频参考需要 vae（H3 视频 VAE）。")
        video_data, audio_tracks = [], []
        # Decode and validate every video before any VAE/CLIP invocation.
        for (port, video), (_, duration) in zip(groups["video"], durations["video"]):
            components = video.get_components()
            frames = components.images
            if frames.ndim != 4 or frames.shape[0] < 1 or frames.shape[-1] not in (3, 4):
                raise ValueError(f"{port}：无法解码有效视频帧。")
            if Fraction(components.frame_rate) <= 0:
                raise ValueError(f"{port}：解码视频帧率无效。")
            soundtrack = components.audio if use_video_audio else None
            if soundtrack is not None:
                audio_tracks.append((port + ".audio", audio_duration(soundtrack, port + ".audio")))
            video_data.append((port, frames, components.frame_rate, duration, soundtrack))
        report["standalone_audios"] = len(groups["audio"])
        report["video_audio_tracks"] = len(audio_tracks)
        report.update(validate_combined_audio(audio_tracks + durations["audio"]))
        if groups["audio"] or any(item[-1] is not None for item in video_data):
            if audio_vae is MISSING or audio_vae is None:
                raise ValueError("音频参考或视频自带音轨需要 audio_vae（H3 音频 VAE）。")

        latent, _ = h3._empty_av_latent(width, height, length)
        ref_items, ref_blocks, labels, video_report = [], [], {}, []
        audio_index = 0
        for image_index, (port, image) in enumerate(groups["image"], 1):
            h, w = image.shape[1:3]
            scale = (min(1.0, math.sqrt(width * height / (w * h))) if ref_image_size == "match"
                     else min(1.0, h3.REF_IMAGE_SHORT_EDGE / min(w, h)))
            tw = max(h3.CANVAS_MULTIPLE, round(w * scale / h3.CANVAS_MULTIPLE) * h3.CANVAS_MULTIPLE)
            th = max(h3.CANVAS_MULTIPLE, round(h * scale / h3.CANVAS_MULTIPLE) * h3.CANVAS_MULTIPLE)
            image = h3._resize(image, tw, th, "disabled")
            z = vae.encode(image)
            ref_items.append({"type": "image", "data": image})
            ref_blocks.append({"kind": "image", "latent_h": th // 16, "latent_w": tw // 16, "latent": z})
            labels[port] = f"<Picture {image_index}>"

        for video_index, (port, frames, fps, duration, soundtrack) in enumerate(video_data, 1):
            vh, vw = frames.shape[1:3]
            cw, ch = h3.adapt_canvas(vw, vh)
            if vw * vh < cw * ch:
                cw = max(h3.CANVAS_MULTIPLE, round(vw / h3.CANVAS_MULTIPLE) * h3.CANVAS_MULTIPLE)
                ch = max(h3.CANVAS_MULTIPLE, round(vh / h3.CANVAS_MULTIPLE) * h3.CANVAS_MULTIPLE)
            frames, content_frames, padded_frames = resample_reference_frames(frames, fps, duration)
            frames = h3._resize(frames, cw, ch, "disabled")
            z = vae.encode(frames)
            audio_latent, audio_t = None, 0
            if soundtrack is not None:
                audio_index += 1
                ref_items.append({"type": "audio"})
                labels[port + ".audio"] = f"<Audio {audio_index}>"
                audio_latent, audio_t = h3._encode_ref_audio(audio_vae, soundtrack)
            # Text-encoder thumbnails use actual content, excluding padding.
            sample_indices = list(range(0, content_frames, h3.FPS // 2))
            ref_items.append({"type": "video", "data": frames[sample_indices],
                              "timestamps": [i / h3.FPS for i in sample_indices]})
            ref_blocks.append({"kind": "video_audio" if audio_t else "video",
                               "latent_t": z.shape[2], "latent_h": ch // 16, "latent_w": cw // 16,
                               "ref_audio_t": audio_t, "latent": z, "audio_latent": audio_latent})
            labels[port] = f"<Video {video_index}>"
            video_report.append({"port": port, "source_fps": float(fps),
                                 "seconds": float(duration), "content_frames_24fps": content_frames,
                                 "tail_padding_frames": padded_frames})

        for port, audio in groups["audio"]:
            audio_index += 1
            ref_items.append({"type": "audio"})
            z, audio_t = h3._encode_ref_audio(audio_vae, audio)
            ref_blocks.append({"kind": "audio", "ref_audio_t": audio_t, "audio_latent": z})
            labels[port] = f"<Audio {audio_index}>"

        tokens = clip.tokenize(prompt, minimax_ref_items=ref_items)
        positive = clip.encode_from_tokens_scheduled(tokens)
        if ref_blocks:
            positive = node_helpers.conditioning_set_values(positive, {"minimax_refs": ref_blocks})
        report.update({"status": "passed", "labels": labels, "videos_detail": video_report})
        text = json.dumps(report, ensure_ascii=False, indent=2)
        return io.NodeOutput(positive, latent, text, ui=ui.PreviewText(text))

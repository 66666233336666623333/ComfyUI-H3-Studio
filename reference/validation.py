"""Validate all reference media before invoking any H3 encoder."""

from fractions import Fraction
import math


PORTS = {"image": 9, "audio": 3, "video": 3}


def _duration(value, port):
    seconds = float(value)
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError(f"{port}：无法读取有效时长。")
    return Fraction(str(seconds)).limit_denominator(1_000_000_000)


def audio_duration(audio, port):
    waveform = audio["waveform"]
    rate = audio["sample_rate"]
    if (waveform.ndim != 3 or waveform.shape[0] != 1
            or waveform.shape[1] < 1 or waveform.shape[2] < 1):
        raise ValueError(f"{port}：每个音频口只接一段音频，波形应为 [1, 声道数, 采样数]。")
    if isinstance(rate, bool) or int(rate) != rate or rate <= 0:
        raise ValueError(f"{port}：音频采样率必须为正整数。")
    return Fraction(int(waveform.shape[-1]), int(rate))


def validate_combined_audio(durations):
    total = sum((duration for _, duration in durations), Fraction(0))
    sources = "；".join(f"{port}={float(duration):.9g}秒" for port, duration in durations)
    if len(durations) > 3 or total > 15:
        raise ValueError(f"合并音频超限：共 {len(durations)} 段、{float(total):.9g} 秒，"
                         f"最多 3 段、合计 15 秒。来源：{sources}。不会自动丢弃任何音频。")
    for port, duration in durations:
        if not 2 <= duration <= 15:
            raise ValueError(f"{port}：时长 {float(duration):.9g} 秒，要求每段 2–15 秒。")
    return {"audios": len(durations), "audio_seconds": float(total),
            "audio_sources": [{"source": port, "seconds": float(duration)}
                              for port, duration in durations]}


def validate_references(inputs):
    groups = {kind: [] for kind in PORTS}
    durations = {"audio": [], "video": []}
    for key in inputs:
        for kind, maximum in PORTS.items():
            if key.startswith(kind + "_") and key not in {
                f"{kind}_{i}" for i in range(1, maximum + 1)
            }:
                raise ValueError(f"未知参考输入 {key}，{kind} 最多 {maximum} 个。")

    # Count first, so oversized mixed inputs fail without decoding any videos.
    for kind, maximum in PORTS.items():
        groups[kind] = [(f"{kind}_{i}", inputs[f"{kind}_{i}"])
                        for i in range(1, maximum + 1)
                        if inputs.get(f"{kind}_{i}") is not None]
    total = sum(len(group) for group in groups.values())
    if total > 12:
        raise ValueError(f"参考文件共 {total} 个，混合输入最多 12 个（视频自带音轨不另计文件）。")

    for port, image in groups["image"]:
        if (image.ndim != 4 or image.shape[0] != 1
                or min(image.shape[1:3]) < 1 or image.shape[-1] not in (3, 4)):
            raise ValueError(f"{port}：每个图像口只接一张 RGB/RGBA 图片；图片批次请拆到独立输入口。")

    for port, audio in groups["audio"]:
        durations["audio"].append((port, audio_duration(audio, port)))
    for port, video in groups["video"]:
        duration = _duration(video.get_duration(), port)
        rate = Fraction(video.get_frame_rate())
        if rate <= 0:
            raise ValueError(f"{port}：视频帧率必须大于 0。")
        durations["video"].append((port, duration))

    for kind, label in (("audio", "音频"), ("video", "视频")):
        for port, duration in durations[kind]:
            if not 2 <= duration <= 15:
                raise ValueError(f"{port}：时长 {float(duration):.9g} 秒，要求每段 2–15 秒。")
        total_duration = sum((duration for _, duration in durations[kind]), Fraction(0))
        if total_duration > 15:
            raise ValueError(f"{label}总时长 {float(total_duration):.9g} 秒，最多 15 秒。")

    report = {
        "files": total,
        "images": len(groups["image"]),
        "videos": len(groups["video"]),
        "audios": len(groups["audio"]),
        "video_seconds": float(sum((d for _, d in durations["video"]), Fraction(0))),
        "audio_seconds": float(sum((d for _, d in durations["audio"]), Fraction(0))),
    }
    return groups, durations, report

"""Expand the integrated panel into existing native nodes."""
import json
from pathlib import Path
from comfy_execution.graph_utils import GraphBuilder
from .core import PRESETS, duration_frames

TEMPLATES = json.loads((Path(__file__).parent / "native_defaults.json").read_text(encoding="utf-8"))

def build_pipeline(options, prompt, references, control, prefix=None):
    g = GraphBuilder(prefix=prefix)
    def native(old_id, **overrides):
        template = TEMPLATES[str(old_id)]
        values = dict(template["inputs"])
        values.update(overrides)
        return g.node(template["class_type"], id=str(old_id), **values)
    width, height = PRESETS[options["resolution"]]
    target, frames = duration_frames(options["duration_seconds"])
    fast = options["enable_fasth3"]
    fun = options["enable_funcontrol"] and not fast
    turbo = options["enable_lora"] and not fast
    clip = native(35, clip_name=options["clip_name"])
    vae = native(33, vae_name=options["video_vae"])
    audio_vae = native(34, vae_name=options["audio_vae"])
    refs = g.node("H3StudioReferenceLoader", id="refs", **references)
    ref_inputs = {}
    index = 0
    for kind, count in [("image", 9), ("audio", 3), ("video", 3)]:
        for number in range(1, count+1):
            ref_inputs[f"{kind}_{number}"] = refs.out(index)
            index += 1
    cond = g.node("H3StudioReferenceConditioning", id="conditioning",
        clip=clip.out(0), vae=vae.out(0), audio_vae=audio_vae.out(0),
        prompt=prompt, width=width, height=height, length=frames, ref_image_size="match",
        use_video_audio=refs.out(15), **ref_inputs)
    model = native(768 if fast else 1, unet_name=options["fasth3_model"] if fast else options["minimax_model"])
    if fast:
        model = native(772, model=model.out(0))
        model = native(771, model=model.out(0))
        model = native(770, model=model.out(0))
    elif turbo:
        model = native(2, model=model.out(0), lora_name=options["lora_name"], strength_model=options["lora_strength"])
    if fun:
        if not control or not control.get("file"):
            raise ValueError("FunControl 已开启，请先选择控制视频。")
        video = native(730, file=control["file"])
        sliced = native(759, video=video.out(0), start_time=control["start_time"], duration=control["duration"])
        sampled = native(758, video=sliced.out(0), num_frames=frames, seed=options["seed"])
        components = g.node("GetVideoComponents", id="components", video=sampled.out(0))
        resized = native(744, input=components.out(0))
        detector = native(748, unet_name=options["detector_model"])
        boxes = native(742, model=detector.out(0), image=resized.out(0))
        pose_model = native(747, ckpt_name=options["pose_model"])
        points = native(745, model=pose_model.out(0), vae=pose_model.out(2),
                        image=resized.out(0), bboxes=boxes.out(0))
        pose = native(743, keypoints=points.out(0))
        patch = native(752, name=options["funcontrol_model"])
        model = native(259, model=model.out(0), model_patch=patch.out(0), vae=vae.out(0),
                       control_video=pose.out(0), strength=options["funcontrol_strength"])
    else:
        pose = g.node("EmptyImage", id="control_off", width=64, height=64, batch_size=1, color=0)
    steps = options["fast_steps"] if fast else options["lora_steps"] if turbo else options["normal_steps"]
    guider = g.node("BasicGuider", id="guider", model=model.out(0), conditioning=cond.out(0))
    noise = g.node("RandomNoise", id="noise", noise_seed=options["seed"])
    sampler = native(255)
    scheduler = native(258, model=model.out(0), steps=steps)
    sampled = g.node("SamplerCustomAdvanced", id="sampler", noise=noise.out(0),
        guider=guider.out(0), sampler=sampler.out(0), sigmas=scheduler.out(0), latent_image=cond.out(1))
    images = g.node("VAEDecode", id="decode_video", samples=sampled.out(0), vae=vae.out(0))
    audio = g.node("VAEDecodeAudio", id="decode_audio", samples=sampled.out(0), vae=audio_vae.out(0))
    video = native(755, images=images.out(0), audio=audio.out(0))
    return g.finalize(), (video.out(0), pose.out(0))

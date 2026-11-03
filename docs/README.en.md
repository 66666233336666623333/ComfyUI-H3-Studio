# H3 Studio — English quick start

A six-node workbench for ComfyUI's native MiniMax H3 pipeline, including FastH3, optional acceleration LoRA / FunControl, image/audio/video reference selection, text-file prompts and output previews. The current node interface is Chinese.

1. Use a ComfyUI build with native MiniMax H3, FunControl, RT-DETR, SDPose, Model Attention Backend and Block Sparse Attention. The checked baseline is `v0.43.0-10-gc7bd15c2`, Python 3.12. Older versions may lack required nodes.
2. Clone this repository into `ComfyUI/custom_nodes/comfyui-h3-studio`, then restart ComfyUI and refresh the browser. Install only one H3 Studio copy. No additional pip packages or separate reference-guard node pack are required beyond the compatible ComfyUI environment.
3. Prepare the [models](MODELS.md), then drag [H3_Studio.json](../examples/H3_Studio.json) into ComfyUI. Confirm every active model choice before running.
4. The example starts with FastH3, 960×544, 5 requested seconds, seed 0 and empty references. The generic prompt describes a misty lake. No private media is included.

FastH3 ON selects dedicated FastH3 weights, VSA 10%, 8 default steps, and sigma shifts 12 / 3. LoRA and FunControl are excluded in this mode. With FastH3 OFF, ordinary H3 can use a compatible acceleration LoRA and/or FunControl. Disabling FunControl omits its entire native load/process/apply branch; old process caches remain managed by ComfyUI.

Reference slots support up to 9 images / 3 audio clips / 3 videos, at most 12 enabled files total. Audio and video clips must be 2–15 seconds each, with a 15-second total per modality. Enabled video soundtracks count toward the combined 3-track / 15-second audio budget. References and pose-control video are separate inputs.

Duration uses the native 24 fps, upward `17k+5` frame bins: 5 requested seconds become 124 frames (~5.17 s); 15 become 362 frames (~15.08 s). No exact-duration trimming is added. Blank output directory means ComfyUI's configured output; relative subdirectories and absolute output paths are supported.

Text prompts accept TXT, Markdown and other listed text formats, up to 4 MiB. UTF-8/16/32, ASCII and GB2312/GBK/GB18030 are supported; choose the exact encoding manually when automatic detection is ambiguous.

**Preview release:** current public-package checks do not run model generation. Long reference videos can cause high memory/attention costs and prolonged waits; this is a known unresolved performance limitation. See [validation](VALIDATION.md) and [attention notes](ATTENTION.md).

Original workbench files are [MIT](../LICENSE). The bundled native-derived conditioning implementation remains GPL-3.0-only. Read [license scope](../THIRD_PARTY_NOTICES.md); the combined package is not MIT-only. Model weights are not bundled.

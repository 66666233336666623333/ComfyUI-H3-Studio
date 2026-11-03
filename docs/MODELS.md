# 模型与依赖

本工作流使用 ComfyUI 的原生 H3 节点，不要求安装 VideoX-Fun、VideoHelperSuite 或另一个参考选通插件。完整 ComfyUI 环境及其原生依赖仍然必需。

以下是公开示例使用的文件名。它们是明确的模型配置示例，不是自动下载声明；请根据对应发布者的说明、许可证和硬件兼容性准备权重，再在控制台选择实际文件。模型若放在子文件夹内，下拉框中需选带该子目录的条目。

| 用途 | ComfyUI 模型目录 | 示例文件名 | 需要条件 |
| --- | --- | --- | --- |
| 普通 H3 | `models/diffusion_models` | `minimax_h3_ref2va_int8_convrot.safetensors` | FastH3 关闭 |
| FastH3 | `models/diffusion_models` | `fasth3_omniref_qad_nvfp4_comfy.safetensors` | FastH3 开启 |
| 文本编码器 | `models/text_encoders` | `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` | 所有模式 |
| 视频 VAE | `models/vae` | `minimax_h3_video_vae_fp16.safetensors` | 所有模式 |
| 音频 VAE | `models/vae` | `minimax_h3_audio_vae_fp32.safetensors` | 所有模式 |
| 加速 LoRA | `models/loras` | `minimax_h3_ref2v_turbo_8step_v1.1_768p_comfyui_bf16.safetensors` | 普通 H3 + LoRA |
| FunControl | `models/model_patches` | `minimax_h3_fun_controlnet_union_2.0_pruned_int8_convrot.safetensors` | 普通 H3 + FunControl |
| 人体检测 | `models/diffusion_models` | `rt_detr_v4-x-hgnet_fp16.safetensors` | 普通 H3 + FunControl |
| 姿态模型 | `models/checkpoints` | `sdpose_wholebody_fp16.safetensors` | 普通 H3 + FunControl |

发布者入口：[ComfyUI 官方模板](https://github.com/Comfy-Org/workflow_templates)、[ComfyUI 原生 H3 实现](https://github.com/Comfy-Org/ComfyUI/blob/master/comfy_extras/nodes_minimax_h3.py)、[FastVideo](https://github.com/hao-ai-lab/FastVideo)。以发布者当前的 ComfyUI 模型说明为准；文件名相近不保证权重可互换。本包没有验证所有 H3 衍生模型。

FastH3 权重必须与 VSA 推理结构匹配。普通 MiniMax H3 的 NVFP4 文件不是 FastH3。FastH3 开启时，普通模型、LoRA 和 FunControl 权重不会被当前展开图加载；仅为关闭的选项保留文件名不会强迫这些文件参与推理。

NVFP4、INT8 以及稀疏内核支持取决于 GPU、ComfyUI、PyTorch 和 Comfy Kitchen 组合。仅成功导入节点不代表硬件已经支持所有量化内核。较小显存机器首先使用短视频与少量参考，避免将长参考视频作为首次测试。

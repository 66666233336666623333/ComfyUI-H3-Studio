# 采样器、注意力后端与稀疏策略

## 先区分三个位置

- **采样器**（KSampler / KSamplerSelect）：控制去噪步骤如何迭代，例如 Euler、DPM++、本工作流的 `res_multistep`。
- **调度器**：控制每一步使用的噪声水平，本工作流使用 `simple`，FastH3 另有视频 / 音频 Sigma Shift 12 / 3。
- **注意力**：控制模型在单次前向里如何关联各个位置。普通后端决定“怎样计算”；稀疏策略还会决定“哪些关系精算、哪些近似”。

采样器里的 `euler`、`dpmpp_2m` 等名称不是注意力机制。也不要把 `karras` 调度器当成某种 Flash / Sage 后端。

## 稠密注意力后端

| 选项 | 做法 | 使用考虑 |
| --- | --- | --- |
| PyTorch / SDPA | 由 PyTorch 根据张量、硬件和可用内核选择 Flash、内存高效或数学实现 | 兼容性基线；不是“必然慢的朴素 attention”，也不保证永远走 Flash |
| FlashAttention | 分块、融合并减少显存读写，避免完整物化巨大的注意力矩阵 | 经典 FP16/BF16 版本属于精确 attention 的高效实现；版本/精度不同仍有数值差别，需匹配硬件 |
| xFormers | 提供内存高效 attention 等内核，按输入选实现 | 取决于 PyTorch / CUDA / Python 编译兼容性；安装了包不等于扩展能加载 |
| Comfy Kitchen attention | 当前原生节点选择 Comfy Kitchen 的 INT8 量化注意力 | 使用量化提高计算效率，有数值近似；本工作流将它用作 FastH3 的稠密后备实现 |
| SageAttention 1 / 2 / 2++ / 3 | 使用量化与误差控制加速 QK / PV；不同代使用 INT8、INT4、FP8 或 FP4 等组合 | 有精度/吞吐/安装支持差别；不能因 GPU 新就直接断言某一代最佳，也不能将稠密 Sage 当作 VSA 的同义词 |

PyTorch 文档说明 SDPA 会自动选用受支持实现，不同内核可能产生浮点差异。[PyTorch SDPA](https://docs.pytorch.org/docs/stable/generated/torch.nn.functional.scaled_dot_product_attention.html)。FlashAttention 的原论文强调 IO 优化和精确 attention；不意味着所有后续低精度变体都位级相同。[FlashAttention](https://github.com/Dao-AILab/flash-attention)。

SageAttention3 针对 Blackwell 的 FP4 Tensor Core；上游仍建议精度敏感应用优先考虑更准确的 SageAttention2。需另外核实具体 ComfyUI 接入、操作系统和安装版本。[SageAttention](https://github.com/thu-ml/SageAttention)。

## 原生 Model Sparse Attention 的三个方法

| 方法 | 如何减少计算 | 与本工作流的关系 |
| --- | --- | --- |
| `sol-attn` | 按当前分数分布动态选块；`tau` 越高通常越稀疏 | 原生描述为免训练近似方案。可以作为普通模型的实验选项，但本包没有把它设为默认，也没有验证画质收益 |
| `sla` | 按评分保留固定比例的 key blocks，并结合近似分支处理其余贡献 | 应使用按此模式训练 / 蒸馏的模型或 LoRA；普通“8 步加速 LoRA”不自动等于 SLA LoRA |
| `vsa` | 按视频三维小块组织注意力，配合训练对应的粗粒度分支 | FastH3 专用配置；本工作流保留 10%，需要匹配 FastH3 权重 |

这三个名称来自[原生稀疏注意力节点](https://github.com/Comfy-Org/ComfyUI/blob/c7bd15c28213348d72042ba0675747f1ebbed95f/comfy_extras/nodes_sparse_attention.py)。`keep_percent=10` 是特定块选择比例，**不是总计算量或显存用量只剩 10%**；文本、参考、音频、粗粒度处理、VAE 和模型权重仍有开销。

FastH3 路径中同时存在 `ModelAttentionBackend` 和 `BlockSparseAttention` 并不冲突：符合条件时用 VSA；未启用稀疏、序列过短或不支持的调用退回稠密后端。当前模板阈值是 `min_tokens=12288`，所以很小的画面或很短的序列也可能回到稠密计算。Kitchen 不可用时，原生后端节点会尝试退回 PyTorch；这不保证必需的 VSA 稀疏内核也能在该硬件上运行。[后端节点源码](https://github.com/Comfy-Org/ComfyUI/blob/c7bd15c28213348d72042ba0675747f1ebbed95f/comfy_extras/nodes_model_advanced.py)。

## 16 GB RTX 50 系列的起点

- FastH3 使用对应权重 + VSA 10% + Kitchen 稠密后备 + 默认 8 步，保持 `res_multistep` / `simple` 与 Sigma Shift 12 / 3 的既有组合。不要为追求速度随意混换稀疏模式，也不要叠加普通 H3 的加速 LoRA。
- 普通 H3 先用当前 ComfyUI 默认后端。需要检查某个后端是否导致异常时，PyTorch SDPA 是有用的对照；它不是对所有硬件最快的保证。
- xFormers 只有扩展正常加载时才值得比较。开发环境的已装包与 Python / PyTorch 不匹配，所以该环境下暂不把它作为可用选项。
- SageAttention 可以作为后续单独测试项；本包未验证它与这些 H3 权重、长参考视频以及当前 Windows 环境的组合，不承诺替换后更快或稳定。
- 先控制生成长度、画面尺寸和参考视频体量，再比较后端。特别是长参考视频，其开销不会因为关闭 FunControl 消失。[已知限制](VALIDATION.md)。

这里给出的是基于工作流结构和已观察环境的配置起点，不是针对各后端的同机跑分排名。没有为本文运行新的生成或性能基准。

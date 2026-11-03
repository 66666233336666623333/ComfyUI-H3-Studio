# License scope and third-party notices

The repository contains original MIT-licensed work and a GPL-licensed derived source file. The package metadata uses `MIT AND GPL-3.0-only` to describe the combined contents, not a choice between licenses.

| Files | License / origin |
| --- | --- |
| Original workbench, UI, loader, validation, examples, tests and documentation, unless marked otherwise | MIT; see [LICENSE](LICENSE) |
| `reference/conditioning.py` | GPL-3.0-only; derived from ComfyUI's `comfy_extras/nodes_minimax_h3.py`, with multi-reference validation, reference labels, soundtrack handling and duration-preserving resampling changes |
| `LICENSES/GPL-3.0.txt` | Full GPL v3 license text retained from ComfyUI |

Upstream source: [ComfyUI native MiniMax H3](https://github.com/Comfy-Org/ComfyUI/blob/c7bd15c28213348d72042ba0675747f1ebbed95f/comfy_extras/nodes_minimax_h3.py). Copyright remains with the respective ComfyUI contributors. Upstream license: [ComfyUI LICENSE](https://github.com/Comfy-Org/ComfyUI/blob/c7bd15c28213348d72042ba0675747f1ebbed95f/LICENSE). The derived file was adapted for this public package on 2026-11-03; its complete corresponding source is included here.

The MIT grant does not remove GPL obligations on the derived file or on combinations to which GPL applies. Do not redistribute that file under MIT alone.

ComfyUI, Comfy Kitchen, PyTorch and other runtime dependencies are separate projects and retain their own licenses. This repository invokes their installed APIs; it does not bundle their model weights or binary distributions. Model licenses and use conditions remain those of their respective publishers.

No generated examples, third-party media, personal reference assets or trained model weights are included. The workflow overview SVG and neutral prompt are original documentation assets.

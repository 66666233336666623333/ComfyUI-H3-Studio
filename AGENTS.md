# Agent guide

## Scope and architecture

This repository contains a ComfyUI custom-node extension and portable example workflows. Read README.md and THIRD_PARTY_NOTICES.md first. Use the user's ComfyUI Python environment for edits and checks; in the maintainer's conda setup, activate `comfyui` before workspace writes.

- `nodes.py`: five user-facing workbench nodes.
- `pipeline.py` + `native_defaults.json`: expand only selected native-node branches.
- `reference/`: bundled loaders, limits and conditioning. Keep these internal node IDs namespaced with H3Studio.
- `js/`: prompt upload, reference selection and preview UI.
- `core.py`: text decoding, output paths and native duration bins.
- `examples/`: sanitized UI workflow, API graph and generic prompt.
- `tests/unit`: standard-library tests; `tests/integration`: existing ComfyUI checkout required.

## Invariants

- Do not edit ComfyUI core, other node packs, user workflows or user media as part of this extension's changes.
- FunControl OFF must omit its entire load/process/apply branch. A zero strength is not an equivalent implementation.
- FastH3 uses its own weights, VSA pattern and sigma shift; it overrides the LoRA and FunControl switches. Do not mix ordinary H3 weights into this branch.
- Preserve reference selection, sparse slot positions, prompt-file encodings, video previews and configurable output directory.
- Keep the 24 fps / upward 17k+5 duration rule. Do not introduce exact-duration trimming unless requested.
- Disabled reference slots must not read their paths. Resolve uploads within the ComfyUI input directory.
- Keep frontend and named / positional workflow widget values consistent.
- Do not queue image, video or audio model generation, download models, restart a user's server or update their environment without task authorization. Lightweight tests use CPU and fake encoders.

## Checks

```shell
python -B -m unittest discover -s tests/unit -v
node --test tests/test_selector_state.mjs
node --check js/studio.js
node --check js/selector.js
```

For integration checks set `COMFYUI_PATH` to a compatible ComfyUI source directory, then run:

```shell
python -B -m unittest discover -s tests/integration -v
```

Integration tests use synthetic tiny media and no model weights. They may emit warnings from installed dependencies; distinguish those from failed assertions. Never describe graph/schema tests as generation or visual-quality verification.

## Publishing

Publish only repository sources, examples, docs and tests. Do not add private prompts, reference paths, local absolute paths, generated media/metadata, logs, tokens, personal email addresses, model weights or environment folders. Keep `.gitignore` exclusions. Use a public GitHub noreply address for commits when desired.

MIT covers new original files; `reference/conditioning.py` retains GPL-3.0-only with provenance in THIRD_PARTY_NOTICES.md and the full GPL text. Preserve that distinction in code, docs and package metadata. Do not represent the entire combined package as MIT-only.

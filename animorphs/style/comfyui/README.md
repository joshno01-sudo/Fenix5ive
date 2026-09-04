# ComfyUI pack — Timm-style Animorphs renders

Everything needed to generate the six kids in a Bruce Timm / DCAU look with
ComfyUI, using the hand-built line drawings in `guides/` as ControlNet
references so the AI output keeps the model-sheet framing, head angle and
silhouette we already approved on the boards.

This lives in the repo because the cloud sandbox that produced the boards has
no GPU and no ComfyUI install. Run this on a machine that does.

## Files

| File | What it is |
| --- | --- |
| `timm_character_sheet.api.json` | The workflow (ComfyUI API format): SDXL checkpoint → style LoRA → Canny ControlNet from a guide image → KSampler → save |
| `prompts.json` | The style prompt, the negative prompt, and a subject line + seed per character |
| `guides/<key>-head.png` | 1024×1024 black-on-white line guide per character, three-quarter head |
| `guides/<key>-figure.png` | 832×1216 line guide per character, full figure |
| `queue_prompts.py` | Uploads the guide, fills the workflow per character, queues it, downloads the result to `out/` |

## Models to put in place

Edit the three file names at the top of the workflow to match what you have:

| Node | Field | What to use |
| --- | --- | --- |
| `1` CheckpointLoaderSimple | `ckpt_name` | Any SDXL 1.0 checkpoint. The base model is fine; a flat-colour / western-cartoon SDXL finetune gets closer with less LoRA weight. Goes in `models/checkpoints/`. |
| `2` LoraLoader | `lora_name` | A Bruce Timm / DCAU / *Batman: The Animated Series* style LoRA for SDXL. Search Civitai or Hugging Face for "Bruce Timm style SDXL" or "DCAU style"; rename or point the field at whatever you download. Goes in `models/loras/`. Strength 0.8–0.9 is the sweet spot; above 1.0 every face becomes Batman. |
| `7` ControlNetLoader | `control_net_name` | An SDXL Canny ControlNet (xinsir's `controlnet-canny-sdxl-1.0` or the diffusers one). Goes in `models/controlnet/`. |

No custom nodes are required. Everything in the workflow ships with a stock
ComfyUI install (`Canny` is a core node).

## Running it

Interactive: open ComfyUI, **Workflow → Open**, pick
`timm_character_sheet.api.json` (recent ComfyUI accepts API-format JSON),
upload a guide from `guides/` into the LoadImage node, paste a subject line
from `prompts.json` in front of the style prompt, queue.

Batch, all six heads:

```bash
python3 queue_prompts.py --server http://127.0.0.1:8188
python3 queue_prompts.py --server http://127.0.0.1:8188 --figures   # full bodies
python3 queue_prompts.py --only rachel cassie --seed 12             # a subset, one seed
python3 queue_prompts.py --dry-run                                  # just print the filled prompts
```

Results land in `out/animorphs_timm/`. Only the Python standard library is used.

## Dials that matter

- **ControlNet strength** (`8` → `strength`, default 0.55, ends at 70 % of the
  steps). Higher keeps the guide's exact jaw and hair silhouette but fights the
  LoRA; lower lets the LoRA redraw the face freely. 0.45–0.65 is the range.
- **LoRA strength** (`2`, default 0.85). See above.
- **CFG** 5–7. Timm's flat colour wants low CFG; high CFG adds shading.
- **Canny thresholds** (`6`). The guides are clean black-on-white, so the
  defaults are already generous; raise the low threshold if you see the
  eye-white edges being traced too literally.
- **Seeds** are fixed per character in `prompts.json` so a re-run reproduces
  the last approved image; pass `--seed` to explore.

## Why guides, and not prompts alone

Prompting "Bruce Timm style" without a reference gives an adult superhero
face nine times out of ten. The guide fixes the framing, the three-quarter
angle, the jaw line and each kid's hair shape, and leaves the LoRA to do what
it is good at: the paint, the eye treatment and the line quality. It also
keeps the six heads consistent with each other, which a pure text prompt
never does.

#!/usr/bin/env python3
"""Queue the six Animorphs character renders on a ComfyUI server.

Usage:
    python3 queue_prompts.py --server http://127.0.0.1:8188            # heads
    python3 queue_prompts.py --server http://127.0.0.1:8188 --figures  # full bodies
    python3 queue_prompts.py --server ... --only jake rachel --seed 7

What it does, per character:
  1. uploads the matching line guide from ./guides to the server's input folder,
  2. fills the workflow's positive prompt, seed, guide image and output prefix,
  3. POSTs the workflow to /prompt, then waits for the image and downloads it
     into ./out/.

Only the standard library is used. Model file names live at the top of
timm_character_sheet.api.json; edit them there to match what is in your
ComfyUI models folders (see README.md).
"""
import argparse
import copy
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))


def load_json(name):
    with open(os.path.join(HERE, name)) as f:
        return json.load(f)


def upload_image(server, path):
    boundary = uuid.uuid4().hex
    name = os.path.basename(path)
    with open(path, "rb") as f:
        data = f.read()
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{name}"\r\n'
        f"Content-Type: image/png\r\n\r\n"
    ).encode() + data + f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"{server}/upload/image", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)["name"]


def queue(server, workflow, client_id):
    req = urllib.request.Request(
        f"{server}/prompt",
        data=json.dumps({"prompt": workflow, "client_id": client_id}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)["prompt_id"]


def wait_for(server, prompt_id, timeout=900):
    t0 = time.time()
    while time.time() - t0 < timeout:
        with urllib.request.urlopen(f"{server}/history/{prompt_id}", timeout=60) as r:
            hist = json.load(r)
        if prompt_id in hist:
            return hist[prompt_id]
        time.sleep(2)
    raise TimeoutError(f"{prompt_id} did not finish in {timeout}s")


def download(server, info, out_dir):
    saved = []
    for node in info.get("outputs", {}).values():
        for img in node.get("images", []):
            q = urllib.parse.urlencode({"filename": img["filename"], "subfolder": img.get("subfolder", ""),
                                        "type": img.get("type", "output")})
            with urllib.request.urlopen(f"{server}/view?{q}", timeout=120) as r:
                data = r.read()
            dst = os.path.join(out_dir, img["filename"])
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "wb") as f:
                f.write(data)
            saved.append(dst)
    return saved


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default=os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188"))
    ap.add_argument("--figures", action="store_true", help="full-body renders instead of heads")
    ap.add_argument("--only", nargs="*", help="character keys to render (default: all six)")
    ap.add_argument("--seed", type=int, help="override every seed")
    ap.add_argument("--dry-run", action="store_true", help="print the filled workflows, do not contact the server")
    args = ap.parse_args()

    base = load_json("timm_character_sheet.api.json")
    base.pop("_comment", None)
    prompts = load_json("prompts.json")
    keys = args.only or list(prompts["characters"])
    client_id = uuid.uuid4().hex
    out_dir = os.path.join(HERE, "out")
    server = args.server.rstrip("/")

    if not args.dry_run:
        try:
            with urllib.request.urlopen(f"{server}/system_stats", timeout=10) as r:
                stats = json.load(r)
            dev = stats.get("devices", [{}])[0]
            print(f"ComfyUI at {server}: {dev.get('name', 'unknown device')}")
        except (urllib.error.URLError, OSError) as e:
            sys.exit(f"cannot reach ComfyUI at {server}: {e}")

    for key in keys:
        c = prompts["characters"][key]
        wf = copy.deepcopy(base)
        subject = c["subject"]
        guide = c["guide"]
        if args.figures:
            subject += ", " + prompts["figures"]["suffix"]
            guide = guide.replace("-head", "-figure")
            wf["9"]["inputs"].update(width=832, height=1216)
        wf["3"]["inputs"]["text"] = f"{subject}, {prompts['style']}"
        wf["4"]["inputs"]["text"] = prompts["negative"]
        wf["10"]["inputs"]["seed"] = args.seed if args.seed is not None else c["seed"]
        wf["12"]["inputs"]["filename_prefix"] = f"animorphs_timm/{key}{'_figure' if args.figures else ''}"
        guide_path = os.path.join(HERE, "guides", guide)
        if args.dry_run:
            print(json.dumps({key: wf["3"]["inputs"]["text"], "guide": guide_path}, indent=1))
            continue
        if not os.path.isfile(guide_path):
            sys.exit(f"missing guide image {guide_path}; run ../render_styleboards.py guides")
        wf["5"]["inputs"]["image"] = upload_image(server, guide_path)
        pid = queue(server, wf, client_id)
        print(f"{key}: queued {pid} ...", end=" ", flush=True)
        info = wait_for(server, pid)
        for p in download(server, info, out_dir):
            print(os.path.relpath(p, HERE))


if __name__ == "__main__":
    main()

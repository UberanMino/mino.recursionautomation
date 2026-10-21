#!/usr/bin/env python3
"""Dropbox + Make queue helpers (all traffic goes through the two mino.recursion Make webhooks).

Webhook URLs come from env (MR_DROPBOX_HOOK, MR_QUEUE_HOOK) or config.local.json (gitignored):
  dropbox_hook : Make scenario "mino.recursion – Dropbox links (Claude)"  ops: link | upload | list,
                 restricted to paths under /mino.recursion/
  queue_hook   : Make scenario "mino.recursion – Queue füllen (Claude)"   adds a record to the
                 mino_recursion_queue data store; "Reel-Queue posten FB+IG" publishes due records
"""
import json
import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def config():
    cfg = {}
    p = os.path.join(ROOT, "config.local.json")
    if os.path.exists(p):
        cfg.update(json.load(open(p)))
    cfg["dropbox_hook"] = os.environ.get("MR_DROPBOX_HOOK", cfg.get("dropbox_hook"))
    cfg["queue_hook"] = os.environ.get("MR_QUEUE_HOOK", cfg.get("queue_hook"))
    if not cfg["dropbox_hook"] or not cfg["queue_hook"]:
        raise SystemExit("missing webhook config: set MR_DROPBOX_HOOK / MR_QUEUE_HOOK or write config.local.json")
    return cfg


def _post_json(url, payload, timeout=120):
    r = subprocess.run(["curl", "-sS", "-m", str(timeout), "-X", "POST", "-H", "Content-Type: application/json",
                        "--data-binary", json.dumps(payload), url], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"POST {url} failed: {r.stderr}")
    return r.stdout


def dropbox(op, path):
    out = _post_json(config()["dropbox_hook"], {"op": op, "path": path})
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        raise RuntimeError(f"dropbox {op} {path}: unexpected response {out[:300]!r}")


def upload(local, dropbox_path):
    link = dropbox("upload", dropbox_path)["link"]
    r = subprocess.run(["curl", "-sS", "-m", "900", "--retry", "3", "-X", "POST", "-H", "Content-Type: application/octet-stream",
                        "--data-binary", "@" + local, link], capture_output=True, text=True)
    if r.returncode != 0 or "content-hash" not in r.stdout:
        raise RuntimeError(f"upload failed: {r.stdout[:300]} {r.stderr[:300]}")
    return dropbox_path


def download(dropbox_path, local):
    link = dropbox("link", dropbox_path)["link"]
    os.makedirs(os.path.dirname(local), exist_ok=True)
    subprocess.run(["curl", "-sS", "-m", "900", "--retry", "3", "-o", local, link], check=True)
    return local


def listdir(dropbox_path):
    return [e["name"] for e in dropbox("list", dropbox_path).get("entries", [])]


def enqueue(key, due_ts, video_id, dropbox_path, caption, title, thumb_ms=600):
    out = _post_json(config()["queue_hook"], {"key": key, "due_ts": int(due_ts), "video_id": video_id,
                                              "dropbox_path": dropbox_path, "caption": caption, "title": title,
                                              "thumb_ms": int(thumb_ms)})
    if "queued" not in out:
        raise RuntimeError(f"enqueue failed: {out[:300]}")
    return out

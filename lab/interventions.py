#!/usr/bin/env python3
"""Build experimental model artifacts as isolated, documented edits of a COPY of the baseline GGUF.

The original Ollama blob is never opened for writing. Each condition starts from a fresh
copy-on-write clone (`cp -c`) of the read-only baseline reference and edits tensors in place.

Only tensors stored unquantized in the GGUF are edited (F32 RMSNorm gain vectors), so an edit is an
exact, direct change to base weights with no re-quantization side effect. The Q4_K/Q6_K matrices
are left untouched (editing them would require de-/re-quantization, which would confound the edit).

usage: interventions.py build <condition_id>|all      (writes artifacts/<id>.gguf + manifests/conditions/<id>.json)
       interventions.py verify                         (re-hash baseline + source blob)
"""
import hashlib, json, os, shutil, subprocess, sys, time
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE_BLOB = os.path.expanduser("~/.ollama/models/blobs/sha256-3d0b790534fe4b79525fc3692950408dca41171676ed7e21db57af5c65ef6ab6")
BASELINE = os.path.join(ROOT, "artifacts", "baseline.gguf")
BASELINE_SHA = "3d0b790534fe4b79525fc3692950408dca41171676ed7e21db57af5c65ef6ab6"
ART = os.path.join(ROOT, "artifacts")
MAN = os.path.join(ROOT, "manifests", "conditions")
CONFIG = os.path.join(ROOT, "manifests", "intervention_config.json")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""): h.update(b)
    return h.hexdigest()


def load_config():
    return json.load(open(CONFIG))


def tensor_names(spec):
    return [f"blk.{i}.{spec['module']}.weight" for i in spec["layers"]]


def apply_edit(path, spec):
    """Edit tensors in place in `path`. Returns per-tensor records."""
    import gguf
    r = gguf.GGUFReader(path, "r+")
    by = {t.name: t for t in r.tensors}
    recs = []
    for li, name in zip(spec["layers"], tensor_names(spec)):
        t = by[name]
        assert t.tensor_type.name == "F32", f"{name} is {t.tensor_type.name}; only unquantized F32 tensors are edited"
        w = np.array(t.data, dtype=np.float32, copy=True)
        before = hashlib.sha256(w.tobytes()).hexdigest()
        m = spec["method"]
        if m == "noop":
            new = w * np.float32(1.0)
        elif m == "scale":            # uniform gain change: w' = w * (1 + eps)
            new = w * np.float32(1.0 + spec["eps"])
        elif m == "random_sign":      # matched random control: w' = w * (1 + eps * s_i), s_i = +-1
            rng = np.random.default_rng([spec["seed"], li])
            s = rng.integers(0, 2, size=w.shape).astype(np.float32) * 2 - 1
            new = w * (np.float32(1.0) + np.float32(spec["eps"]) * s)
        else:
            raise ValueError(m)
        new = new.astype(np.float32)
        t.data[...] = new
        d = (new.astype(np.float64) - w.astype(np.float64))
        recs.append({"tensor": name, "dtype": "F32", "shape": [int(x) for x in t.shape], "n_elements": int(w.size),
                     "data_offset": int(t.data_offset), "sha256_before": before,
                     "sha256_after": hashlib.sha256(new.tobytes()).hexdigest(),
                     "delta_l2": float(np.sqrt((d ** 2).sum())), "weight_l2_before": float(np.sqrt((w.astype(np.float64) ** 2).sum())),
                     "mean_before": float(w.mean()), "mean_after": float(new.mean())})
    r.data.flush()
    del r
    return recs


def build(cid, cfg=None, keep=True):
    cfg = cfg or load_config()
    c = next(x for x in cfg["conditions"] if x["id"] == cid)
    os.makedirs(ART, exist_ok=True); os.makedirs(MAN, exist_ok=True)
    out = os.path.join(ART, cid + ".gguf")
    if not os.path.exists(BASELINE):   # (re)create the read-only reference clone from the untouched source blob
        subprocess.run(["cp", "-c", SOURCE_BLOB, BASELINE], check=True); os.chmod(BASELINE, 0o444)
    assert sha256(BASELINE) == BASELINE_SHA, "baseline reference changed!"
    if os.path.realpath(out) != os.path.realpath(BASELINE) and os.path.exists(out):
        os.chmod(out, 0o644); os.remove(out)
    man = {"id": cid, "type": c["type"], "label": c["label"], "built_from": "artifacts/baseline.gguf",
           "baseline_sha256": BASELINE_SHA, "method": c["method"], "spec": c.get("spec"), "tensors": [], "steps": []}
    if c["method"] == "unchanged":
        assert os.path.realpath(out) == os.path.realpath(BASELINE), "the unchanged condition must be the baseline reference itself"
        man["steps"].append("the read-only baseline reference itself (copy-on-write clone of the Ollama blob); no bytes written")
    else:
        subprocess.run(["cp", "-c", BASELINE, out], check=True); os.chmod(out, 0o644)
        spec = c["spec"]
        if c["method"] == "edit":
            man["tensors"] = apply_edit(out, spec)
            man["steps"].append(f"in-place edit: {spec['method']} on {len(man['tensors'])} tensors")
        elif c["method"] == "edit_then_rollback":
            import gguf
            r = gguf.GGUFReader(out, "r"); by = {t.name: t for t in r.tensors}
            saved = {n: np.array(by[n].data, dtype=np.float32, copy=True) for n in tensor_names(spec)}
            del r
            man["tensors"] = apply_edit(out, spec)
            man["sha256_after_edit_before_rollback"] = sha256(out)
            man["steps"].append(f"in-place edit: {spec['method']} on {len(man['tensors'])} tensors (sha recorded)")
            r = gguf.GGUFReader(out, "r+"); by = {t.name: t for t in r.tensors}
            for n, w in saved.items(): by[n].data[...] = w
            r.data.flush(); del r
            man["steps"].append("rollback: original tensor bytes (saved before the edit) written back")
        tot = float(np.sqrt(sum(t["delta_l2"] ** 2 for t in man["tensors"])))
        base = float(np.sqrt(sum(t["weight_l2_before"] ** 2 for t in man["tensors"])))
        man["total_delta_l2"] = tot; man["relative_delta_l2"] = tot / base if base else 0.0
        man["n_elements_edited"] = int(sum(t["n_elements"] for t in man["tensors"]))
    os.chmod(out, 0o444)
    man["artifact"] = f"artifacts/{cid}.gguf"; man["artifact_sha256"] = sha256(out)
    man["artifact_bytes"] = os.path.getsize(out)
    man["identical_to_baseline"] = man["artifact_sha256"] == BASELINE_SHA
    man["built_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    json.dump(man, open(os.path.join(MAN, cid + ".json"), "w"), indent=1)
    if not keep: os.remove(out)
    return man


if __name__ == "__main__":
    if sys.argv[1] == "verify":
        print("source blob :", sha256(SOURCE_BLOB)); print("baseline    :", sha256(BASELINE)); print("expected    :", BASELINE_SHA)
    else:
        cfg = load_config()
        ids = [c["id"] for c in cfg["conditions"]] if sys.argv[2] == "all" else sys.argv[2:]
        for cid in ids:
            m = build(cid, cfg)
            print(f"{cid:22s} {m['type']:12s} sha={m['artifact_sha256'][:16]} identical_to_baseline={m['identical_to_baseline']} rel_delta={m.get('relative_delta_l2', 0):.4f}")

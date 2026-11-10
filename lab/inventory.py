#!/usr/bin/env python3
"""Record the baseline inventory: model identity, files, checksums, runtime and hardware. Writes manifests/baseline.json."""
import collections, json, os, platform, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core, interventions


def sh(cmd):
    try: return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception as ex: return f"unavailable: {ex}"


def main():
    import gguf, numpy
    r = gguf.GGUFReader(interventions.SOURCE_BLOB)
    meta = {}
    for k, f in r.fields.items():
        if k.startswith("tokenizer.ggml.token") or k in ("tokenizer.ggml.merges",): meta[k] = f"<{len(f.data)} entries>"; continue
        try: v = f.contents()
        except Exception: v = "?"
        meta[k] = v if isinstance(v, (int, float, bool)) else str(v)[:200]
    types = collections.Counter(t.tensor_type.name for t in r.tensors)
    by_mod = collections.defaultdict(collections.Counter)
    for t in r.tensors:
        mod = t.name.split(".")[-2] if t.name.startswith("blk.") else t.name.rsplit(".", 1)[0]
        by_mod[mod][t.tensor_type.name] += 1
    blobs = os.path.expanduser("~/.ollama/models/blobs")
    man_path = os.path.expanduser("~/.ollama/models/manifests/registry.ollama.ai/library/qwen3/1.7b")
    om = json.load(open(man_path))
    inv = {
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "model": {"name": "qwen3:1.7b (Ollama library tag)", "gguf_general_name": meta.get("general.name"), "architecture": meta.get("general.architecture"),
                  "parameters_label": meta.get("general.size_label"), "blocks": meta.get("qwen3.block_count"), "hidden_size": meta.get("qwen3.embedding_length"),
                  "ffn_size": meta.get("qwen3.feed_forward_length"), "attention_heads": meta.get("qwen3.attention.head_count"), "kv_heads": meta.get("qwen3.attention.head_count_kv"),
                  "context_length": meta.get("qwen3.context_length"), "license": "Apache-2.0 (license text shipped as an Ollama layer)",
                  "ollama_manifest_digest": "8f68893c685c3ddff2aa3fffce2aa60a30bb2da65ca488b61fff134a4d1730e7"},
        "files": {"source_blob": interventions.SOURCE_BLOB, "source_blob_sha256": interventions.sha256(interventions.SOURCE_BLOB),
                  "source_blob_bytes": os.path.getsize(interventions.SOURCE_BLOB), "source_blob_mtime": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(os.path.getmtime(interventions.SOURCE_BLOB))),
                  "baseline_reference": "artifacts/baseline.gguf (APFS copy-on-write clone, mode 0444)", "baseline_reference_sha256": interventions.sha256(interventions.BASELINE),
                  "ollama_layers": [{"mediaType": l["mediaType"], "digest": l["digest"], "size": l["size"]} for l in om["layers"]]},
        "quantization": {"file_type": meta.get("general.file_type"), "file_type_name": "Q4_K_M (mostly Q4_K)", "tensor_types": dict(types),
                         "by_module": {k: dict(v) for k, v in sorted(by_mod.items())},
                         "directly_editable": "F32 tensors (RMSNorm gains: attn_norm, ffn_norm, attn_q_norm, attn_k_norm, output_norm) and F16 attn_v matrices can be edited exactly in place. "
                                              "Q4_K/Q6_K matrices cannot be edited exactly: a change must be de-quantized and re-quantized, which itself perturbs every weight in the block."},
        "tokenizer": {"model": meta.get("tokenizer.ggml.model"), "pre": meta.get("tokenizer.ggml.pre"), "vocab": meta.get("tokenizer.ggml.tokens"),
                      "eos": meta.get("tokenizer.ggml.eos_token_id"), "chat_template": "none embedded in GGUF; the runner builds ChatML prompts itself (lab/core.py chatml)"},
        "gguf_metadata": meta,
        "runtime": {"inference": "llama.cpp llama-server", "llama_cpp_version": sh("llama-server --version 2>&1 | head -2"), "ollama_version": sh("ollama --version 2>&1 | tail -1"),
                    "python": sys.version.split()[0], "gguf_py": getattr(gguf, "__version__", sh(f"{sys.executable} -m pip show gguf | grep Version")), "numpy": numpy.__version__,
                    "server_args": core.SERVER_ARGS, "inference_settings": core.INFER, "thinking": "disabled for every condition by pre-filling an empty <think></think> block"},
        "hardware": {"chip": sh("sysctl -n machdep.cpu.brand_string"), "cores": sh("sysctl -n hw.ncpu"), "performance_cores": sh("sysctl -n hw.perflevel0.physicalcpu"),
                     "memory_bytes": int(sh("sysctl -n hw.memsize") or 0), "os": sh("sw_vers -productName") + " " + sh("sw_vers -productVersion"), "machine": platform.machine(),
                     "disk_free": sh("df -h ~ | tail -1 | awk '{print $4}'")},
    }
    os.makedirs(os.path.join(core.ROOT, "manifests"), exist_ok=True)
    json.dump(inv, open(os.path.join(core.ROOT, "manifests", "baseline.json"), "w"), indent=1)
    print(json.dumps({k: inv[k] for k in ("model", "quantization", "hardware")}, indent=1)[:2500])


if __name__ == "__main__":
    main()

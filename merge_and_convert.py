"""
merge_and_convert.py
Merges the LoRA adapter into the base model and converts to GGUF.

Run once:
    pip install transformers peft torch safetensors sentencepiece gguf
    python merge_and_convert.py
"""

import os
import sys
import torch
from pathlib import Path

SCRIPT_DIR    = Path(__file__).parent
ADAPTER_PATH  = SCRIPT_DIR / "echo_lora_download" / "checkpoint-381"
MERGED_PATH   = SCRIPT_DIR / "echo_merged_local"
GGUF_PATH     = SCRIPT_DIR / "echo-finetuned.gguf"
BASE_MODEL    = "Qwen/Qwen2.5-1.5B-Instruct"
LLAMA_CPP_DIR = SCRIPT_DIR / "llama.cpp"

print(f"Adapter: {ADAPTER_PATH}")
print(f"Merged output: {MERGED_PATH}")
print(f"GGUF output: {GGUF_PATH}")

# ── Step 1: Load base model + merge adapter ───────────────────────────────────
print("\n[1/3] Loading base model...")
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)

model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL,
    torch_dtype=torch.float16,
    device_map="cpu",
    low_cpu_mem_usage=True,
)

print("[1/3] Applying LoRA adapter and merging...")
peft_model = PeftModel.from_pretrained(model, str(ADAPTER_PATH))
merged = peft_model.merge_and_unload()
merged = merged.to(torch.float16)

print("[1/3] Saving merged model...")
MERGED_PATH.mkdir(exist_ok=True)
merged.save_pretrained(str(MERGED_PATH), safe_serialization=True)
tokenizer.save_pretrained(str(MERGED_PATH))
print(f"[1/3] Saved to {MERGED_PATH}")

del merged, peft_model, model

# ── Step 2: Clone llama.cpp if not present ────────────────────────────────────
print("\n[2/3] Setting up llama.cpp...")
if not LLAMA_CPP_DIR.exists():
    ret = os.system(f'git clone https://github.com/ggerganov/llama.cpp "{LLAMA_CPP_DIR}" --depth 1')
    if ret != 0:
        print("ERROR: git clone failed. Is git installed?")
        sys.exit(1)

ret = os.system(f'pip install -r "{LLAMA_CPP_DIR / "requirements.txt"}" -q')

# ── Step 3: Convert to GGUF ───────────────────────────────────────────────────
print("\n[3/3] Converting to GGUF (f16)...")
convert_script = LLAMA_CPP_DIR / "convert_hf_to_gguf.py"
cmd = f'python "{convert_script}" "{MERGED_PATH}" --outtype f16 --outfile "{GGUF_PATH}"'
ret = os.system(cmd)

if ret == 0 and GGUF_PATH.exists():
    size_mb = GGUF_PATH.stat().st_size / 1024 / 1024
    print(f"\nDone. GGUF saved: {GGUF_PATH} ({size_mb:.0f} MB)")
    print("\nNext steps:")
    print("  1. Update Modelfile: FROM ./echo-finetuned.gguf")
    print("  2. ollama create echo -f Modelfile")
    print("  3. Test: ollama run echo")
else:
    print("\nERROR: Conversion failed. Check output above.")

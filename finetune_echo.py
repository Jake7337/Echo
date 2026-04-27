"""
finetune_echo.py
LoRA fine-tune Qwen2.5-7B on Echo's personality dataset using Unsloth.
Outputs a merged model ready to convert for Ollama.

Requirements (run setup_finetune.bat first):
    conda activate echo_finetune
    python finetune_echo.py

Output:
    echo_model/  — merged model weights
"""

import json
import os
import torch
from datasets import Dataset
from unsloth import FastLanguageModel
from trl import SFTTrainer
from transformers import TrainingArguments

# ── Config ─────────────────────────────────────────────────────────────────────

DATASET_FILE  = os.path.join(os.path.dirname(__file__), "echo_dataset.json")
OUTPUT_DIR    = os.path.join(os.path.dirname(__file__), "echo_model")
LORA_DIR      = os.path.join(os.path.dirname(__file__), "echo_lora")

MODEL_NAME    = "unsloth/Qwen2.5-7B-Instruct-bnb-4bit"  # 4-bit quantized, fits 3060 12GB
MAX_SEQ_LEN   = 2048
LORA_RANK     = 16     # 16 is solid for personality fine-tune
BATCH_SIZE    = 2      # safe for 12GB VRAM
GRAD_ACCUM    = 4      # effective batch size = 8
EPOCHS        = 5
LEARNING_RATE = 2e-4

# ── Alpaca prompt template ─────────────────────────────────────────────────────

ALPACA_TEMPLATE = """Below is an instruction that describes who you are, paired with an input that provides context. Write a response that completes the request.

### Instruction:
{instruction}

### Input:
{input}

### Response:
{output}"""

ALPACA_TEMPLATE_NO_INPUT = """Below is an instruction that describes who you are. Write a response that completes the request.

### Instruction:
{instruction}

### Response:
{output}"""

EOS_TOKEN = None  # set after model loads


def format_examples(examples):
    texts = []
    for instruction, input_text, output in zip(
        examples["instruction"], examples["input"], examples["output"]
    ):
        if input_text.strip():
            text = ALPACA_TEMPLATE.format(
                instruction=instruction,
                input=input_text,
                output=output,
            )
        else:
            text = ALPACA_TEMPLATE_NO_INPUT.format(
                instruction=instruction,
                output=output,
            )
        texts.append(text + EOS_TOKEN)
    return {"text": texts}


def main():
    global EOS_TOKEN

    print(f"GPU: {torch.cuda.get_device_name(0)}", flush=True)
    print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB", flush=True)
    print(f"Loading model: {MODEL_NAME}", flush=True)

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=MODEL_NAME,
        max_seq_length=MAX_SEQ_LEN,
        dtype=None,       # auto-detect
        load_in_4bit=True,
    )

    EOS_TOKEN = tokenizer.eos_token

    model = FastLanguageModel.get_peft_model(
        model,
        r=LORA_RANK,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        lora_alpha=16,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=42,
    )

    # ── Load dataset ───────────────────────────────────────────────────────────
    print(f"Loading dataset from {DATASET_FILE}", flush=True)
    with open(DATASET_FILE, "r", encoding="utf-8") as f:
        raw = json.load(f)

    print(f"Examples: {len(raw)}", flush=True)
    dataset = Dataset.from_list(raw)
    dataset = dataset.map(format_examples, batched=True)

    # ── Train ──────────────────────────────────────────────────────────────────
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=MAX_SEQ_LEN,
        dataset_num_proc=2,
        args=TrainingArguments(
            per_device_train_batch_size=BATCH_SIZE,
            gradient_accumulation_steps=GRAD_ACCUM,
            warmup_steps=10,
            num_train_epochs=EPOCHS,
            learning_rate=LEARNING_RATE,
            fp16=not torch.cuda.is_bf16_supported(),
            bf16=torch.cuda.is_bf16_supported(),
            logging_steps=10,
            optim="adamw_8bit",
            weight_decay=0.01,
            lr_scheduler_type="cosine",
            output_dir=LORA_DIR,
            save_strategy="epoch",
        ),
    )

    print("Starting training...", flush=True)
    trainer.train()
    print("Training complete.", flush=True)

    # ── Save ───────────────────────────────────────────────────────────────────
    print(f"Saving LoRA adapter to {LORA_DIR}", flush=True)
    model.save_pretrained(LORA_DIR)
    tokenizer.save_pretrained(LORA_DIR)

    print(f"Merging and saving full model to {OUTPUT_DIR}", flush=True)
    model.save_pretrained_merged(OUTPUT_DIR, tokenizer, save_method="merged_16bit")

    print("Done. Model ready at:", OUTPUT_DIR, flush=True)
    print("Next: convert to GGUF and load into Ollama.", flush=True)


if __name__ == "__main__":
    main()

"""Generate finetune/ostutor_qlora_colab.ipynb and finetune/finetune_qlora_colab.py from ONE source.

    python finetune/make_notebook.py

Why a generator: the notebook and the script used to be edited by hand separately and drifted apart.
Every cell below is the single source of truth for both files.
"""
import json
import pathlib
import re

HERE = pathlib.Path(__file__).parent

TITLE = """# OSTutor: QLoRA fine-tune of Qwen2.5-3B-Instruct (free Colab T4)

Teaches the tutor model to answer **from the retrieved course context**, to answer **exactly what is asked**
(one number, a Gantt chart only, a comparison, a yes/no), and to **use only the simulator's numbers**.
The training records are written in the same prompt format the app sends at run time.

**Before you start**
1. Runtime menu -> *Change runtime type* -> **T4 GPU** -> Save.
2. Have `train.jsonl` and `val.jsonl` ready (from `data/processed/`). You will be asked to upload them in step 3.
3. Run the cells **top to bottom**. Total time is roughly 25-40 minutes.

**What you get at the end:** `ostutor_export.zip` containing `ostutor-q4_k_m.gguf` and a ready `Modelfile`.
Unzip it into `finetune/` on your laptop and run `ollama create ostutor -f Modelfile`.

If a cell fails, read the *Troubleshooting* note at the bottom before changing anything."""

CELLS = [
("markdown", TITLE),

("markdown", "## 1. Check the GPU"),
("code", '''import subprocess
gpu = subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True).stdout
assert "GPU" in gpu, "No GPU found. Runtime -> Change runtime type -> T4 GPU, Save, then run this cell again."
print(gpu)'''),

("markdown", "## 2. Install\n\nTakes 2-4 minutes. If Colab then says *restart session*, restart and continue from step 3 (do not re-run this cell)."),
("code", '''!pip install -q unsloth'''),

("markdown", "## 3. Upload and check the data\n\nSelect `train.jsonl` and `val.jsonl` when the file picker opens. Skips the upload if the files are already here."),
("code", '''import json, os

NEED = ["train.jsonl", "val.jsonl"]
if not all(os.path.exists(f) for f in NEED):
    from google.colab import files
    print("Select train.jsonl and val.jsonl from data/processed/ on your laptop:")
    files.upload()

def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]

for f in NEED:
    assert os.path.exists(f), f"{f} was not uploaded. Run this cell again and select both files."
train_rows, val_rows = read_jsonl("train.jsonl"), read_jsonl("val.jsonl")

# Every record must be system -> user -> assistant with real text in each turn.
for name, rows in (("train", train_rows), ("val", val_rows)):
    for i, r in enumerate(rows):
        roles = [m["role"] for m in r["messages"]]
        assert roles == ["system", "user", "assistant"], f"{name}[{i}] has roles {roles}"
        assert all(m["content"].strip() for m in r["messages"]), f"{name}[{i}] has an empty turn"
print(f"train: {len(train_rows)} records   validation: {len(val_rows)} records")

# Guard against uploading an OLD copy of the data (an earlier version had only 236 plain records).
with_context = sum("Context from the course material" in r["messages"][1]["content"] for r in train_rows)
assert len(train_rows) >= 800 and with_context >= 500, (
    f"This looks like an OLD train.jsonl ({len(train_rows)} records, {with_context} with course context). "
    "Use the new files from ~/Downloads: train.jsonl is about 3.3 MB (924 records), val.jsonl about 371 KB.")
print("data version OK:", with_context, "records carry retrieved course context")'''),

("markdown", "## 4. Load the model\n\nQwen2.5-3B-Instruct is a plain text model (no image processor), so tokenizing and chat templates behave predictably. It is also the model the app already runs locally."),
("code", '''import torch
from unsloth import FastLanguageModel
from unsloth.chat_templates import get_chat_template

BASE_MODEL = "unsloth/Qwen2.5-3B-Instruct"
MAX_SEQ_LEN = 3072

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=BASE_MODEL, max_seq_length=MAX_SEQ_LEN, dtype=None, load_in_4bit=True)
tokenizer = get_chat_template(tokenizer, chat_template="qwen-2.5")   # ChatML: <|im_start|>role ... <|im_end|>

model = FastLanguageModel.get_peft_model(
    model, r=16, lora_alpha=32, lora_dropout=0, bias="none",
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    use_gradient_checkpointing="unsloth", random_state=42)
print("model ready:", BASE_MODEL)'''),

("markdown", "## 5. Prepare the text and check it really tokenized\n\nThe length check calls the tokenizer with `text=`, which is correct for every kind of tokenizer. A bare `tokenizer(text)` on a multimodal processor treats the string as an *image*, which is how an earlier run reported `max 1, mean 1` and trained on nothing."),
("code", '''from datasets import Dataset

def render(r):
    return tokenizer.apply_chat_template(r["messages"], tokenize=False, add_generation_prompt=False)

def n_tokens(text):
    return len(tokenizer(text=text, add_special_tokens=False)["input_ids"])

train_text = [render(r) for r in train_rows]
val_text = [render(r) for r in val_rows]
lengths = [n_tokens(t) for t in train_text + val_text]
print(f"token lengths: min {min(lengths)}, mean {sum(lengths)/len(lengths):.0f}, max {max(lengths)}, limit {MAX_SEQ_LEN}")
assert min(lengths) > 50, "Tokenization looks wrong (records are only a few tokens long). Do not train. Check step 4."

# Drop (rather than silently truncate) anything longer than the window.
train_text = [t for t in train_text if n_tokens(t) <= MAX_SEQ_LEN]
val_text = [t for t in val_text if n_tokens(t) <= MAX_SEQ_LEN]
print(f"after length filter: train {len(train_text)}, validation {len(val_text)}")
assert len(train_text) > 100 and len(val_text) > 10, "Too few records left. Check the uploaded files."

print("\\n--- one rendered record (end) ---")
print(train_text[0][-700:])

train_ds = Dataset.from_dict({"text": train_text})
val_ds = Dataset.from_dict({"text": val_text})'''),

("markdown", "## 6. Set up the trainer\n\nThe settings are chosen by looking at what this version of `trl` / `transformers` accepts, because argument names changed between releases (`max_seq_length` / `max_length`, `eval_strategy` / `evaluation_strategy`, `tokenizer` / `processing_class`). The model is trained on the **assistant answer only**, not on the long prompt, and the best epoch by validation loss is kept."),
("code", '''import inspect
from trl import SFTConfig, SFTTrainer
from unsloth.chat_templates import train_on_responses_only

use_bf16 = torch.cuda.is_bf16_supported()
cfg = dict(
    dataset_text_field="text",
    per_device_train_batch_size=2, gradient_accumulation_steps=4,
    num_train_epochs=2, learning_rate=1e-4, warmup_ratio=0.05, lr_scheduler_type="cosine",
    weight_decay=0.01, logging_steps=10,
    save_strategy="epoch", save_total_limit=1,
    load_best_model_at_end=True, metric_for_best_model="eval_loss", greater_is_better=False,
    fp16=not use_bf16, bf16=use_bf16, optim="adamw_8bit", seed=42,
    output_dir="outputs", report_to="none")

fields = set(inspect.signature(SFTConfig.__init__).parameters)
cfg["max_seq_length" if "max_seq_length" in fields else "max_length"] = MAX_SEQ_LEN
cfg["eval_strategy" if "eval_strategy" in fields else "evaluation_strategy"] = "epoch"

trainer_params = set(inspect.signature(SFTTrainer.__init__).parameters)
tok_arg = {"processing_class": tokenizer} if "processing_class" in trainer_params else {"tokenizer": tokenizer}

trainer = SFTTrainer(model=model, train_dataset=train_ds, eval_dataset=val_ds,
                     args=SFTConfig(**cfg), **tok_arg)

# Compute the loss only on the assistant's reply.
trainer = train_on_responses_only(trainer, instruction_part="<|im_start|>user\\n",
                                  response_part="<|im_start|>assistant\\n")

try:   # show exactly what the model will learn from in one record
    labels = [x for x in trainer.train_dataset[0]["labels"] if x != -100]
    print("--- the part of record 0 the loss is computed on ---")
    print(tokenizer.decode(labels)[:500])
except Exception as e:
    print("(could not preview the training target:", type(e).__name__, ")")'''),

("markdown", "## 7. Train\n\nWatch the **validation loss** column: it should fall and then flatten. If it rises while training loss keeps falling, the model is memorising; the best epoch is kept automatically."),
("code", '''stats = trainer.train()

log = trainer.state.log_history
train_curve = [(round(h["epoch"], 2), round(h["loss"], 4)) for h in log if "loss" in h]
eval_curve = [(round(h["epoch"], 2), round(h["eval_loss"], 4)) for h in log if "eval_loss" in h]
print("\\ntraining loss  :", train_curve[-5:])
print("validation loss:", eval_curve)
if len(eval_curve) >= 2 and eval_curve[-1][1] > eval_curve[0][1] + 0.05:
    print("WARNING: validation loss went UP. The best epoch was kept, but consider fewer epochs.")'''),

("markdown", "## 8. Smoke test on held-out examples\n\nThree validation records the model never trained on. Compare its answer with the reference."),
("code", '''FastLanguageModel.for_inference(model)

def ask(messages, max_new_tokens=350):
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(text=prompt, add_special_tokens=False, return_tensors="pt").to("cuda")
    out = model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False, use_cache=True)
    return tokenizer.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)

import random
random.seed(1)
for r in random.sample(val_rows, 3):
    question = r["messages"][1]["content"].split("Student question:")[-1].strip().split("\\n")[0][:150]
    print("QUESTION :", question)
    print("MODEL    :", ask(r["messages"][:2])[:450].replace("\\n", " "))
    print("REFERENCE:", r["messages"][2]["content"][:450].replace("\\n", " "))
    print("-" * 80)'''),

("markdown", "## 9. Export for Ollama\n\nSaves the small LoRA adapter, and a quantised GGUF model plus a `Modelfile` with the correct Qwen chat template."),
("code", '''import glob, os, shutil

model.save_pretrained("ostutor-lora")
tokenizer.save_pretrained("ostutor-lora")

os.makedirs("ostutor_export", exist_ok=True)
model.save_pretrained_gguf("ostutor-gguf", tokenizer, quantization_method="q4_k_m")

# Unsloth names the output differently between versions: find the quantised file wherever it landed.
found = [p for p in glob.glob("**/*.gguf", recursive=True) if "export" not in p]
q4 = [p for p in found if "q4_k_m" in p.lower()] or found
assert q4, "No .gguf file was produced. Download ostutor-lora.zip (cell 10) and ask for help."
target = "ostutor_export/ostutor-q4_k_m.gguf"
shutil.copy(q4[0], target)

MODELFILE = \'\'\'FROM ./ostutor-q4_k_m.gguf

TEMPLATE """{{ if .System }}<|im_start|>system
{{ .System }}<|im_end|>
{{ end }}{{ if .Prompt }}<|im_start|>user
{{ .Prompt }}<|im_end|>
{{ end }}<|im_start|>assistant
{{ .Response }}<|im_end|>
"""

SYSTEM """You are an Operating Systems tutor. Explain CPU scheduling step by step, using only the context provided, and cite the source note."""

PARAMETER stop "<|im_end|>"
PARAMETER stop "<|im_start|>"
PARAMETER temperature 0.2
PARAMETER num_ctx 4096
\'\'\'
with open("ostutor_export/Modelfile", "w") as f:
    f.write(MODELFILE)
print("exported:", target, f"({os.path.getsize(target) / 1e9:.2f} GB)")'''),

("markdown", "## 10. Save to Google Drive, then download\n\nA 2 GB file often fails when downloaded straight from Colab (the connection drops). Copying to your Drive first is reliable: it survives disconnects, and you download from drive.google.com at your own pace. **Run this cell before closing the tab.**"),
("code", '''import os, shutil
from google.colab import drive

shutil.make_archive("ostutor_export", "zip", "ostutor_export")
shutil.make_archive("ostutor-lora", "zip", "ostutor-lora")

drive.mount("/content/drive")
dest = "/content/drive/MyDrive/ostutor"
os.makedirs(dest, exist_ok=True)
for f in ("ostutor_export.zip", "ostutor-lora.zip"):
    shutil.copy(f, os.path.join(dest, f))
    print(f"saved {f}: {os.path.getsize(os.path.join(dest, f)) / 1e6:.0f} MB")
print("\\nDone. Open drive.google.com -> My Drive -> ostutor, right-click ostutor_export.zip -> Download.")'''),

("markdown", """## Troubleshooting

| Message | What it means | What to do |
|---|---|---|
| `No GPU found` | Runtime is CPU-only | Runtime -> Change runtime type -> T4 GPU, then re-run from cell 1 |
| `Tokenization looks wrong` | Text is not being tokenized | Do not train. Re-run cell 4 and 5; confirm `BASE_MODEL` is Qwen2.5 |
| `CUDA out of memory` | Window too large for the T4 | Set `MAX_SEQ_LEN = 2048` in cell 4 (a few long records are dropped) and re-run from cell 4 |
| `No .gguf file was produced` | GGUF export failed | Download `ostutor-lora.zip`; the adapter alone is still a successful result |
| Session disconnected mid-training | Free-tier time limit | Reconnect, re-run from cell 1; training is only ~25-40 minutes |\n| Download stalls or disconnects | A 2 GB browser download is unreliable | Use cell 10 (copies to Google Drive), then download from drive.google.com |"""),
]


def build_notebook():
    cells = []
    for kind, src in CELLS:
        lines = src.split("\n")
        source = [l + "\n" for l in lines[:-1]] + [lines[-1]]
        cell = {"cell_type": kind, "metadata": {}, "source": source}
        if kind == "code":
            cell["execution_count"] = None
            cell["outputs"] = []
        cells.append(cell)
    return {"nbformat": 4, "nbformat_minor": 5,
            "metadata": {"accelerator": "GPU",
                         "colab": {"gpuType": "T4", "provenance": []},
                         "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                         "language_info": {"name": "python"}},
            "cells": cells}


def build_script():
    out = ['"""Generated by finetune/make_notebook.py: identical steps to ostutor_qlora_colab.ipynb.',
           "Run on a machine with a CUDA GPU (Colab T4 is enough); `pip install unsloth` first.",
           'Needs train.jsonl and val.jsonl in the working directory."""', ""]
    for kind, src in CELLS:
        if kind == "markdown":
            out += ["# " + l for l in src.split("\n")[:1]] + [""]
            continue
        for line in src.split("\n"):
            out.append(("# (shell) " + line) if line.startswith("!") else line)
        out.append("")
    return "\n".join(out).replace("from google.colab import files",
                                  "from google.colab import files  # only available inside Colab")


if __name__ == "__main__":
    nb = build_notebook()
    (HERE / "ostutor_qlora_colab.ipynb").write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
    (HERE / "finetune_qlora_colab.py").write_text(build_script(), encoding="utf-8")
    print("wrote ostutor_qlora_colab.ipynb and finetune_qlora_colab.py")

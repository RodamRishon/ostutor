"""One command that rebuilds everything the fine-tune needs, in the right order.

    python build_training_data.py

  1. generate_dataset   raw records (theory, numerical, one-thing questions, checks, refusals) + eval set
  2. build_index        re-index the notes so the generated facts are retrievable
  3. prepare_dataset    dedupe, quality-filter, re-verify every numerical record with the simulator and
                        checker, split train/validation by group, render each record in the app's real
                        prompt format (context + simulator output) -> data/processed/{train,val}.jsonl
"""
import generate_dataset
from build_index import build
from prepare_dataset import run
from rag_format import RagFormatter

if __name__ == "__main__":
    print("== 1. generating raw records ==")
    generate_dataset.main()
    print("\n== 2. rebuilding the knowledge-base index ==")
    build()
    print("\n== 3. validating, splitting and rendering ==")
    fmt = RagFormatter()
    summary = run("data/raw", "data/processed", formatter=fmt)
    print(f"  of which: source passage missing {fmt.missing_source}, longer than the 3000-token window {fmt.too_long}")
    print(f"\ncategories: {', '.join(summary['categories'])}")

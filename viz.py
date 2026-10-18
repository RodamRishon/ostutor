"""Gantt chart and comparison plots for the Streamlit UI."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

PALETTE = ["#4C78A8", "#F58518", "#54A24B", "#B279A2", "#E45756",
           "#72B7B2", "#EECA3B", "#9D755D", "#FF9DA6", "#79706E"]


def gantt_figure(result, width=10, upto=None):
    """Draw the Gantt chart. With `upto` given, only draw what has happened by
    that time (for the step-by-step walkthrough), while keeping the x-axis
    fixed to the full chart so the picture doesn't jump as the student steps
    through it."""
    full = result["gantt"]
    pids = sorted({p for p, _, _ in full if p != "idle"}, key=lambda s: int(s[1:]) if s[1:].isdigit() else 0)
    colour = {p: PALETTE[i % len(PALETTE)] for i, p in enumerate(pids)}
    gantt = full if upto is None else [(p, s, min(e, upto)) for p, s, e in full if s < upto]
    fig, ax = plt.subplots(figsize=(width, 1.5))
    for pid, s, e in gantt:
        if pid == "idle":
            ax.broken_barh([(s, e - s)], (0, 1), facecolors="#eeeeee", edgecolor="#999999", hatch="//")
            ax.text((s + e) / 2, 0.5, "idle", ha="center", va="center", fontsize=8, color="#666666")
        else:
            ax.broken_barh([(s, e - s)], (0, 1), facecolors=colour[pid], edgecolor="white", linewidth=1.5)
            ax.text((s + e) / 2, 0.5, pid, ha="center", va="center", fontsize=10,
                    color="white", fontweight="bold")
    ticks = sorted({t for _, s, e in gantt for t in (s, e)})
    ax.set_xticks(ticks)
    ax.set_xlim(full[0][1], full[-1][2])
    ax.set_yticks([])
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.tick_params(axis="x", labelsize=8)
    fig.tight_layout()
    return fig


def comparison_figure(results):
    """Average waiting / turnaround of every algorithm on the same process set."""
    names = [r["algorithm_name"].replace(" (", "\n(") + (f"\nq={r['quantum']}" if r["quantum"] else "")
             for r in results]
    wait = [r["avg_waiting"] for r in results]
    tat = [r["avg_turnaround"] for r in results]
    fig, ax = plt.subplots(figsize=(10, 3.2))
    x = range(len(results))
    ax.bar([i - 0.2 for i in x], wait, width=0.4, label="avg waiting", color="#4C78A8")
    ax.bar([i + 0.2 for i in x], tat, width=0.4, label="avg turnaround", color="#F58518")
    for i, (w, t) in enumerate(zip(wait, tat)):
        ax.text(i - 0.2, w, f"{w:.2f}", ha="center", va="bottom", fontsize=8)
        ax.text(i + 0.2, t, f"{t:.2f}", ha="center", va="bottom", fontsize=8)
    ax.set_xticks(list(x))
    ax.set_xticklabels(names, fontsize=8)
    ax.set_ylabel("time units")
    ax.legend(frameon=False, fontsize=8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.tight_layout()
    return fig

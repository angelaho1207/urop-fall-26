#!/bin/bash
# Submits the full_post run (design.md G38): 4 workers on mit_preemptable (6 h), 2 on mit_normal_gpu (2 h, backfill as
# G25), and two finisher copies (G26). Called by pilot_post.sbatch when the G36 gate passes.
set -euo pipefail
cd /orcd/home/002/angela_h/urop-fall-26/exp2_rollout_gap
for i in 1 2 3 4; do sbatch -p mit_preemptable --gres=gpu:1 -t 6:00:00 sbatch/worker_post.sbatch; done
for i in 1 2; do sbatch -p mit_normal_gpu --gres=gpu:1 -t 2:00:00 sbatch/worker_post.sbatch; done
sbatch -p mit_preemptable sbatch/finisher_post.sbatch
sbatch -p mit_normal sbatch/finisher_post.sbatch

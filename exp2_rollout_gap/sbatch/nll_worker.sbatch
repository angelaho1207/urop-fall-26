#!/bin/bash
# Garbled check: per-doc NLL worker (design.md G54, G55). Any number at once; each claims parts with lock files (G21).
#   sbatch -p mit_preemptable --gres=gpu:1 sbatch/nll_worker.sbatch
#SBATCH -c 4
#SBATCH --mem=64G
#SBATCH -t 03:00:00
#SBATCH -J exp2_nll_worker
#SBATCH --requeue
#SBATCH --chdir=/orcd/home/002/angela_h/urop-fall-26/exp2_rollout_gap
#SBATCH -o /orcd/home/002/angela_h/urop-fall-26/logs/exp2_nll_worker_%j.out
set -uo pipefail
echo "host: $(hostname)  job: $SLURM_JOB_ID  partition: $SLURM_JOB_PARTITION  gpu: $(nvidia-smi --query-gpu=name --format=csv,noheader)  start: $(date)"
module load miniforge/25.11.0-0
source ~/venvs/cg/bin/activate
python -u s14_nll.py
echo "end: $(date)"

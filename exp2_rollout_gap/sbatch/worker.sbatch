#!/bin/bash
# Full-run worker (design.md G21, G22): generate any unclaimed parts of stage1, then main, then encode parts on disk.
# Any number run at once; each claims parts with lock files. Partition and GPU are given at submit time, e.g.
#   sbatch -p mit_preemptable --gres=gpu:h100:1 sbatch/worker.sbatch
#SBATCH -c 8
#SBATCH --mem=64G
#SBATCH -t 06:00:00
#SBATCH -J exp2_worker
#SBATCH --requeue
#SBATCH --chdir=/orcd/home/002/angela_h/urop-fall-26/exp2_rollout_gap
#SBATCH -o /orcd/home/002/angela_h/urop-fall-26/logs/exp2_worker_%j.out

set -uo pipefail
echo "host: $(hostname)  job: $SLURM_JOB_ID  partition: $SLURM_JOB_PARTITION  gpu: $(nvidia-smi --query-gpu=name --format=csv,noheader)  start: $(date)"
module load miniforge/25.11.0-0
source ~/venvs/cg/bin/activate
for g in stage1 main; do python -u s01_rollouts.py --run full --generator $g 2>&1 | grep --line-buffered -v CUDACachingAllocator; done
for g in stage1 main; do python -u s02_activations.py --run full --generator $g; done
echo "end: $(date)"

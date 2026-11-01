#!/bin/bash
# full_post worker (design.md G21, G22, G33): generate any unclaimed parts of sft, dpo, instruct, then encode the parts
# on disk of main (re-encoded under G34), sft, dpo, instruct. Any number run at once; each claims parts with lock files.
#   sbatch -p mit_preemptable --gres=gpu:1 -t 6:00:00 sbatch/worker_post.sbatch
#SBATCH -c 8
#SBATCH --mem=64G
#SBATCH -t 06:00:00
#SBATCH -J exp2_worker_post
#SBATCH --requeue
#SBATCH --chdir=/orcd/home/002/angela_h/urop-fall-26/exp2_rollout_gap
#SBATCH -o /orcd/home/002/angela_h/urop-fall-26/logs/exp2_worker_post_%j.out

set -uo pipefail
echo "host: $(hostname)  job: $SLURM_JOB_ID  partition: $SLURM_JOB_PARTITION  gpu: $(nvidia-smi --query-gpu=name --format=csv,noheader)  start: $(date)"
module load miniforge/25.11.0-0
source ~/venvs/cg/bin/activate
for g in sft dpo instruct; do python -u s01_rollouts.py --run full_post --generator $g 2>&1 | grep --line-buffered -v CUDACachingAllocator; done
for g in main sft dpo instruct; do python -u s02_activations.py --run full_post --generator $g; done
echo "end: $(date)"

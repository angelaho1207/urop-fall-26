#!/bin/bash
# Full run for one generator (design.md G4, G5, G18): 10,000 rollouts on one H200, then SAE activations (G8).
# Usage: sbatch --export=GEN=stage1 rollouts.sbatch   (or GEN=main). Parts resume, so a resubmit continues.
#SBATCH -p mit_normal_gpu
#SBATCH --gres=gpu:h200:1
#SBATCH -c 8
#SBATCH --mem=64G
#SBATCH -t 06:00:00
#SBATCH -J exp2_roll
#SBATCH --chdir=/orcd/home/002/angela_h/urop-fall-26/exp2_rollout_gap
#SBATCH -o /orcd/home/002/angela_h/urop-fall-26/logs/exp2_full_%x_%j.out
#SBATCH --mail-user=angelaho1207@gmail.com
#SBATCH --mail-type=BEGIN,END,FAIL

set -euo pipefail
echo "host: $(hostname)  job: $SLURM_JOB_ID  gen: $GEN  gpu: $(nvidia-smi --query-gpu=name --format=csv,noheader)  start: $(date)"
module load miniforge/25.11.0-0
source ~/venvs/cg/bin/activate
python -u s01_rollouts.py --run full --generator "$GEN" --batch 96 2>&1 | grep -v CUDACachingAllocator
python -u s02_activations.py --run full --generator "$GEN"
echo "end: $(date)"

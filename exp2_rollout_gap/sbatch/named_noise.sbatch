#!/bin/bash
# Noise rerun of classes and extreme lists, CG App. B.3 (design.md G72). CPU only, no API
#SBATCH -c 2
#SBATCH --mem=48G
#SBATCH -t 4:00:00
#SBATCH -J exp2_named_noise
#SBATCH --requeue
#SBATCH --chdir=/orcd/home/002/angela_h/urop-fall-26/exp2_rollout_gap
#SBATCH -o /orcd/home/002/angela_h/urop-fall-26/logs/exp2_named_noise_%j.out
#SBATCH --mail-user=angelaho1207@gmail.com
#SBATCH --mail-type=END,FAIL
set -euo pipefail
source sbatch/dedupe.sh
dedupe
echo "start: $(date) $(hostname) $SLURM_JOB_PARTITION"
module load miniforge/25.11.0-0
source ~/venvs/cg/bin/activate
python -u s21_named_noise.py
echo "end: $(date)"

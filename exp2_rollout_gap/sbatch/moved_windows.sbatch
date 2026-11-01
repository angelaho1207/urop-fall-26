#!/bin/bash
# Concepts that moved: selection and example windows (design.md G47, G48). CPU only
#SBATCH -c 4
#SBATCH --mem=48G
#SBATCH -t 3:00:00
#SBATCH -J exp2_moved_windows
#SBATCH --requeue
#SBATCH --chdir=/orcd/home/002/angela_h/urop-fall-26/exp2_rollout_gap
#SBATCH -o /orcd/home/002/angela_h/urop-fall-26/logs/exp2_moved_windows_%j.out
#SBATCH --mail-user=angelaho1207@gmail.com
#SBATCH --mail-type=END,FAIL
set -euo pipefail
source sbatch/dedupe.sh
dedupe
echo "start: $(date) $(hostname) $SLURM_JOB_PARTITION"
module load miniforge/25.11.0-0
source ~/venvs/cg/bin/activate
python -u s12_moved_windows.py
echo "end: $(date)"

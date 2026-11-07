#!/bin/bash
# Missing concepts: lists, baseline counts, naming windows, garbled measure, free check, push of counts (design.md G87-G93). No paid call
#SBATCH -p mit_normal
#SBATCH -c 4
#SBATCH --mem=48G
#SBATCH -t 3:00:00
#SBATCH -J exp2_missing_select
#SBATCH --requeue
#SBATCH --chdir=/orcd/home/002/angela_h/urop-fall-26/exp2_rollout_gap
#SBATCH -o /orcd/home/002/angela_h/urop-fall-26/logs/exp2_missing_select_%j.out
#SBATCH --mail-user=angelaho1207@gmail.com
#SBATCH --mail-type=END,FAIL
set -euo pipefail
echo "start: $(date) $(hostname) $SLURM_JOB_PARTITION"
module load miniforge/25.11.0-0
source ~/venvs/cg/bin/activate
python -u s26_missing_select.py
python -u s27_missing_labels.py check
python -u s27_missing_labels.py publish_check
echo "end: $(date)"

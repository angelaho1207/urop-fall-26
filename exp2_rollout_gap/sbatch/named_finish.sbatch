#!/bin/bash
# Finisher of the named run: cost row, report, findings, commit, push (design.md G73). No API
#SBATCH -c 1
#SBATCH --mem=4G
#SBATCH -t 0:30:00
#SBATCH -J exp2_named_finish
#SBATCH --requeue
#SBATCH --chdir=/orcd/home/002/angela_h/urop-fall-26/exp2_rollout_gap
#SBATCH -o /orcd/home/002/angela_h/urop-fall-26/logs/exp2_named_finish_%j.out
#SBATCH --mail-user=angelaho1207@gmail.com
#SBATCH --mail-type=END,FAIL
set -euo pipefail
echo "start: $(date) $(hostname) $SLURM_JOB_PARTITION"
module load miniforge/25.11.0-0
source ~/venvs/cg/bin/activate
python -u s22_named_finish.py
echo "end: $(date)"

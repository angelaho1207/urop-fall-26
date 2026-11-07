#!/bin/bash
# Missing concepts: names, theme scheme, assignments, analysis, cost row, push (design.md G90-G93). Paid API calls, hard stop $24.81 (s13 guard)
#SBATCH -p mit_normal
#SBATCH -c 1
#SBATCH --mem=8G
#SBATCH -t 6:00:00
#SBATCH -J exp2_missing_labels
#SBATCH --requeue
#SBATCH --chdir=/orcd/home/002/angela_h/urop-fall-26/exp2_rollout_gap
#SBATCH -o /orcd/home/002/angela_h/urop-fall-26/logs/exp2_missing_labels_%j.out
#SBATCH --mail-user=angelaho1207@gmail.com
#SBATCH --mail-type=END,FAIL
set -uo pipefail
echo "start: $(date) $(hostname) $SLURM_JOB_PARTITION"
test -f results/full_post_missing_check.json || { echo "free check missing"; exit 1; }
module load miniforge/25.11.0-0
source ~/venvs/cg/bin/activate
python -u s27_missing_labels.py run
status=$?
python -u s27_missing_labels.py publish  # also after a guard stop, so spent dollars are recorded
echo "end: $(date)"
exit $status

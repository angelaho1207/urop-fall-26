#!/bin/bash
# Concepts that moved: names, quiz, judge, analysis (design.md G49-G51). Paid API calls, hard stop $15 (s13 guard)
#SBATCH -c 1
#SBATCH --mem=8G
#SBATCH -t 12:00:00
#SBATCH -J exp2_moved_labels
#SBATCH --requeue
#SBATCH --chdir=/orcd/home/002/angela_h/urop-fall-26/exp2_rollout_gap
#SBATCH -o /orcd/home/002/angela_h/urop-fall-26/logs/exp2_moved_labels_%j.out
#SBATCH --mail-user=angelaho1207@gmail.com
#SBATCH --mail-type=END,FAIL
set -euo pipefail
source sbatch/dedupe.sh
dedupe
echo "start: $(date) $(hostname) $SLURM_JOB_PARTITION"
test -f results/full_post_moved_windows_summary.json || { echo "windows summary missing: s12 did not finish"; exit 1; }
module load miniforge/25.11.0-0
source ~/venvs/cg/bin/activate
python -u s13_moved_labels.py run
echo "end: $(date)"

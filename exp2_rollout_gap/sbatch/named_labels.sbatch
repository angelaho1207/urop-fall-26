#!/bin/bash
# Names per model and class: names, quiz, analysis (design.md G63-G67). Paid API calls, hard stop $35 (s13 guard)
#SBATCH -c 1
#SBATCH --mem=16G
#SBATCH -t 12:00:00
#SBATCH -J exp2_named_labels
#SBATCH --requeue
#SBATCH --chdir=/orcd/home/002/angela_h/urop-fall-26/exp2_rollout_gap
#SBATCH -o /orcd/home/002/angela_h/urop-fall-26/logs/exp2_named_labels_%j.out
#SBATCH --mail-user=angelaho1207@gmail.com
#SBATCH --mail-type=END,FAIL
set -euo pipefail
source sbatch/dedupe.sh
dedupe
echo "start: $(date) $(hostname) $SLURM_JOB_PARTITION"
test -f results/full_post_named_selection_summary.json || { echo "selection summary missing: s19 did not finish"; exit 1; }
module load miniforge/25.11.0-0
source ~/venvs/cg/bin/activate
python -u s20_named_labels.py run
echo "end: $(date)"

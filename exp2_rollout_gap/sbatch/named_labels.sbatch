#!/bin/bash
# Names per model: names, rollout names, quiz, analysis (design.md G70-G73). Paid API calls, hard stop $40 (s13 guard)
#SBATCH -c 1
#SBATCH --mem=8G
#SBATCH -t 6:00:00
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
test -f results/full_post_named_check.json || { echo "free check missing"; exit 1; }
module load miniforge/25.11.0-0
source ~/venvs/cg/bin/activate
python -u s20_named_labels.py run
echo "end: $(date)"

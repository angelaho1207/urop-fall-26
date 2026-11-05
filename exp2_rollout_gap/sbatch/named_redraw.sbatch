#!/bin/bash
# Names per model and class: redraw of the check and its rollout windows (design.md G69). CPU only, no API
#SBATCH -c 4
#SBATCH --mem=48G
#SBATCH -t 3:00:00
#SBATCH -J exp2_named_redraw
#SBATCH --requeue
#SBATCH --chdir=/orcd/home/002/angela_h/urop-fall-26/exp2_rollout_gap
#SBATCH -o /orcd/home/002/angela_h/urop-fall-26/logs/exp2_named_redraw_%j.out
#SBATCH --mail-user=angelaho1207@gmail.com
#SBATCH --mail-type=END,FAIL
set -euo pipefail
source sbatch/dedupe.sh
dedupe
echo "start: $(date) $(hostname) $SLURM_JOB_PARTITION"
module load miniforge/25.11.0-0
source ~/venvs/cg/bin/activate
python -u s19_named_select.py
echo "end: $(date)"

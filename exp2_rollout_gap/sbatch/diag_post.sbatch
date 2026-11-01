#!/bin/bash
# full_post diagnostics (design.md G39-G42, G44-G46): s09, then the G40 figures (new file names only)
#SBATCH -c 4
#SBATCH --mem=64G
#SBATCH -t 4:00:00
#SBATCH -J exp2_diag_post
#SBATCH --requeue
#SBATCH --chdir=/orcd/home/002/angela_h/urop-fall-26/exp2_rollout_gap
#SBATCH -o /orcd/home/002/angela_h/urop-fall-26/logs/exp2_diag_post_%j.out
#SBATCH --mail-user=angelaho1207@gmail.com
#SBATCH --mail-type=END,FAIL
set -euo pipefail
source sbatch/dedupe.sh
dedupe
echo "start: $(date) $(hostname) $SLURM_JOB_PARTITION"
module load miniforge/25.11.0-0
source ~/venvs/cg/bin/activate
python -u s09_diagnostics.py
deactivate  # matplotlib is in the miniforge base env
(cd figures && python make_diagnostics_figures.py --run full_post) 2>&1 | { grep -v findfont || true; }
echo "end: $(date)"

#!/bin/bash
# full_post diagnostics summary (design.md G46), after the diagnostics and both length jobs
#SBATCH -c 1
#SBATCH --mem=4G
#SBATCH -t 0:30:00
#SBATCH -J exp2_diag_summary
#SBATCH --requeue
#SBATCH --chdir=/orcd/home/002/angela_h/urop-fall-26/exp2_rollout_gap
#SBATCH -o /orcd/home/002/angela_h/urop-fall-26/logs/exp2_diag_summary_%j.out
#SBATCH --mail-user=angelaho1207@gmail.com
#SBATCH --mail-type=END,FAIL
set -euo pipefail
source sbatch/dedupe.sh
dedupe
module load miniforge/25.11.0-0
source ~/venvs/cg/bin/activate
python -u s11_diagnostics_summary.py

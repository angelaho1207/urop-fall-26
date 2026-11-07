#!/bin/bash
# Coverage lists: selection, reruns, chi = 0 check, windows, free check, names, analysis, cost row, push (design.md G95-G99).
# Paid API calls only after the free check passes; hard stop $11.14 (s13 guard)
#SBATCH -p mit_normal
#SBATCH -c 4
#SBATCH --mem=64G
#SBATCH -t 4:00:00
#SBATCH -J exp2_coverage
#SBATCH --requeue
#SBATCH --chdir=/orcd/home/002/angela_h/urop-fall-26/exp2_rollout_gap
#SBATCH -o /orcd/home/002/angela_h/urop-fall-26/logs/exp2_coverage_%j.out
#SBATCH --mail-user=angelaho1207@gmail.com
#SBATCH --mail-type=END,FAIL
set -uo pipefail
echo "start: $(date) $(hostname) $SLURM_JOB_PARTITION"
module load miniforge/25.11.0-0
source ~/venvs/cg/bin/activate
python -u s29_coverage_select.py || exit 1
python -u s30_coverage_labels.py check || exit 1   # a failed check stops here, before any money moves
python -u s30_coverage_labels.py run
status=$?
python -u s30_coverage_labels.py publish  # also after a guard stop, so spent dollars are recorded
echo "end: $(date)"
exit $status

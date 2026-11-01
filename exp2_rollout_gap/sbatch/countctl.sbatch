#!/bin/bash
# Doc-count control (design.md G60): tasks 0-19 = seeds, task 20 = check that measure() reproduces noflag.
#   sbatch -p mit_normal --array=0-20 sbatch/countctl.sbatch
#SBATCH -c 4
#SBATCH --mem=16G
#SBATCH -t 01:00:00
#SBATCH -J exp2_countctl
#SBATCH --requeue
#SBATCH --chdir=/orcd/home/002/angela_h/urop-fall-26/exp2_rollout_gap
#SBATCH -o /orcd/home/002/angela_h/urop-fall-26/logs/exp2_countctl_%A_%a.out
#SBATCH --mail-user=angelaho1207@gmail.com
#SBATCH --mail-type=END,FAIL
set -euo pipefail
echo "start: $(date) $(hostname) task $SLURM_ARRAY_TASK_ID"
module load miniforge/25.11.0-0
source ~/venvs/cg/bin/activate
if [ "$SLURM_ARRAY_TASK_ID" -eq 20 ]; then python -u s16_count_control.py --check; else python -u s16_count_control.py --seed "$SLURM_ARRAY_TASK_ID"; fi
echo "end: $(date)"

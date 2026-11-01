#!/bin/bash
# Doc-count control summary (design.md G60), after the array: sbatch -d afterany:<array id> sbatch/countctl_summary.sbatch
#SBATCH -p mit_normal
#SBATCH -c 1
#SBATCH --mem=4G
#SBATCH -t 00:20:00
#SBATCH -J exp2_countctl_summary
#SBATCH --chdir=/orcd/home/002/angela_h/urop-fall-26/exp2_rollout_gap
#SBATCH -o /orcd/home/002/angela_h/urop-fall-26/logs/exp2_countctl_summary_%j.out
#SBATCH --mail-user=angelaho1207@gmail.com
#SBATCH --mail-type=END,FAIL
set -euo pipefail
module load miniforge/25.11.0-0
source ~/venvs/cg/bin/activate
python -u s16_count_control.py --summary

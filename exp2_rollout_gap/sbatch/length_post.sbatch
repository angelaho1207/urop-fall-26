#!/bin/bash
# full_post length checks (design.md G43, G45, G46). Usage: sbatch -J exp2_len_<mode> sbatch/length_post.sbatch <mode>
#SBATCH -c 4
#SBATCH --mem=64G
#SBATCH -t 3:00:00
#SBATCH --requeue
#SBATCH --chdir=/orcd/home/002/angela_h/urop-fall-26/exp2_rollout_gap
#SBATCH -o /orcd/home/002/angela_h/urop-fall-26/logs/exp2_len_post_%j.out
#SBATCH --mail-user=angelaho1207@gmail.com
#SBATCH --mail-type=END,FAIL
set -euo pipefail
source sbatch/dedupe.sh
dedupe
echo "start: $(date) $(hostname) $SLURM_JOB_PARTITION mode $1"
module load miniforge/25.11.0-0
source ~/venvs/cg/bin/activate
python -u s10_length.py --mode "$1"
echo "end: $(date)"

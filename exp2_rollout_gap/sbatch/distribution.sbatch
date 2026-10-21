#!/bin/bash
# Full-run analysis (design.md G9-G17), CPU only. Usage: sbatch --export=DEGEN=<G14 threshold> distribution.sbatch
#SBATCH -p mit_normal
#SBATCH -c 4
#SBATCH --mem=32G
#SBATCH -t 03:00:00
#SBATCH -J exp2_dist
#SBATCH --chdir=/orcd/home/002/angela_h/urop-fall-26/exp2_rollout_gap
#SBATCH -o /orcd/home/002/angela_h/urop-fall-26/logs/exp2_full_%x_%j.out

set -euo pipefail
echo "host: $(hostname)  job: $SLURM_JOB_ID  start: $(date)"
module load miniforge/25.11.0-0
source ~/venvs/cg/bin/activate
python -u s03_distribution.py --run full --degen "$DEGEN"
echo "end: $(date)"

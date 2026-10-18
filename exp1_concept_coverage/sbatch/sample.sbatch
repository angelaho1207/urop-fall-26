#!/bin/bash
# Full-run sampling: s02 on the CPU partition (design.md rows 4-8, T6, T14, T18). Submit from exp1_concept_coverage/sbatch.
#SBATCH -p mit_normal
#SBATCH -c 4
#SBATCH --mem=32G
#SBATCH -t 08:00:00
#SBATCH -J exp1_s02
#SBATCH --chdir=/orcd/home/002/angela_h/urop-fall-26/exp1_concept_coverage
#SBATCH -o /orcd/home/002/angela_h/urop-fall-26/logs/full_s02_%j.out

set -euo pipefail
echo "host: $(hostname)  job: $SLURM_JOB_ID  start: $(date)"
module load miniforge/25.11.0-0
source ~/venvs/cg/bin/activate
python -u s02_sample_docs.py --run full --n-docs 50000 --docs-per-shard 50 --no-min-one-per-source
echo "end: $(date)"

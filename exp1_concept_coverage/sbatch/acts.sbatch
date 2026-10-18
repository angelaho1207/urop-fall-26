#!/bin/bash
# Full-run activations: s04 on one L40S (design.md rows 9-15, T10-T12, T14, T18). Submitted with a dependency on the s02 job.
#SBATCH -p mit_normal_gpu
#SBATCH --gres=gpu:l40s:1
#SBATCH -c 8
#SBATCH --mem=64G
#SBATCH -t 06:00:00
#SBATCH -J exp1_s04
#SBATCH --chdir=/orcd/home/002/angela_h/urop-fall-26/exp1_concept_coverage
#SBATCH -o /orcd/home/002/angela_h/urop-fall-26/logs/full_s04_%j.out

set -euo pipefail
echo "host: $(hostname)  job: $SLURM_JOB_ID  gpu: $(nvidia-smi --query-gpu=name --format=csv,noheader)  start: $(date)"
module load miniforge/25.11.0-0
source ~/venvs/cg/bin/activate
python -u s04_activations.py --run full
echo "end: $(date)"

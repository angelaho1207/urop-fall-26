#!/bin/bash
# Pile reference (design.md R1-R3): sample 40,000 Pile docs (s02b), then SAE activations with yesterday's s04 code.
#SBATCH -p mit_normal_gpu
#SBATCH --gres=gpu:l40s:1
#SBATCH -c 8
#SBATCH --mem=64G
#SBATCH -t 02:00:00
#SBATCH -J exp1_pile
#SBATCH --chdir=/orcd/home/002/angela_h/urop-fall-26/exp1_concept_coverage
#SBATCH -o /orcd/home/002/angela_h/urop-fall-26/logs/pile_%j.out
#SBATCH --mail-user=angelaho1207@gmail.com
#SBATCH --mail-type=BEGIN,END,FAIL

set -euo pipefail
echo "host: $(hostname)  job: $SLURM_JOB_ID  gpu: $(nvidia-smi --query-gpu=name --format=csv,noheader)  start: $(date)"
module load miniforge/25.11.0-0
source ~/venvs/cg/bin/activate
python -u s02b_pile_docs.py --run pile
echo "s02b done: $(date)"
python -u s04_activations.py --run pile
echo "s04 done: $(date)"

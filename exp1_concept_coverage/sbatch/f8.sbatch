#!/bin/bash
# Row F8: seen vs unseen check on one L40S. Pass extra args after the script name, e.g. --rows-per-group 20 for the smoke test.
#SBATCH -p mit_normal_gpu
#SBATCH --gres=gpu:l40s:1
#SBATCH -c 8
#SBATCH --mem=64G
#SBATCH -t 02:00:00
#SBATCH -J exp1_f8
#SBATCH --chdir=/orcd/home/002/angela_h/urop-fall-26/exp1_concept_coverage
#SBATCH -o /orcd/home/002/angela_h/urop-fall-26/logs/f8_%j.out
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=angelaho1207@gmail.com

set -euo pipefail
echo "host: $(hostname)  job: $SLURM_JOB_ID  gpu: $(nvidia-smi --query-gpu=name --format=csv,noheader)  start: $(date)"
module load miniforge/25.11.0-0
source ~/venvs/cg/bin/activate
python -u s10_seen_unseen.py "$@"
echo "end: $(date)"

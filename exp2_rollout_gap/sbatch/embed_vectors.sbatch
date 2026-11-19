#!/bin/bash
# Embedding similarity, step 2: Qwen3-Embedding-8B on every window, concept vectors (design.md G117). One GPU, no API.
# Resumes from its saved state: if it hits the time limit, submit it again (and then embed_analyses.sbatch).
#SBATCH -p mit_normal_gpu
#SBATCH --gres=gpu:1
#SBATCH -c 8
#SBATCH --mem=64G
#SBATCH -t 6:00:00
#SBATCH -J exp2_embed_vectors
#SBATCH -o /orcd/home/002/angela_h/urop-fall-26/logs/exp2_embed_vectors_%j.out
#SBATCH --chdir=/orcd/home/002/angela_h/urop-fall-26/exp2_rollout_gap
#SBATCH --mail-user=angelaho1207@gmail.com
#SBATCH --mail-type=END,FAIL
set -euo pipefail
echo "start: $(date) $(hostname)"
module load miniforge/25.11.0-0
source ~/venvs/cg/bin/activate
echo "gpu: $(nvidia-smi --query-gpu=name --format=csv,noheader)"
python -u s38_embed_vectors.py
echo "end: $(date)"

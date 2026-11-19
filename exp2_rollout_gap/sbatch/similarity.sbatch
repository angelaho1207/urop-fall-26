#!/bin/bash
# Concept similarity: decoder-cosine neighbours, co-movement and substitution tests (design.md G101-G104). CPU, no API
#SBATCH -p mit_normal
#SBATCH -c 4
#SBATCH --mem=16G
#SBATCH -t 1:00:00
#SBATCH -J exp2_similarity
#SBATCH --chdir=/orcd/home/002/angela_h/urop-fall-26/exp2_rollout_gap
#SBATCH -o /orcd/home/002/angela_h/urop-fall-26/logs/exp2_similarity_%j.out
#SBATCH --mail-user=angelaho1207@gmail.com
#SBATCH --mail-type=END,FAIL
set -euo pipefail
echo "start: $(date) $(hostname)"
module load miniforge/25.11.0-0
source ~/venvs/cg/bin/activate
python -u s32_concept_similarity.py
cd .. && git add exp2_rollout_gap/results/full_post_similarity_summary.json exp2_rollout_gap/results/full_post_similarity_summary.md
git commit -m "Exp 2 concept similarity: neighbours, co-movement and substitution results (G101-G104)" && git pull --rebase --quiet && git push --quiet
echo "end: $(date)"

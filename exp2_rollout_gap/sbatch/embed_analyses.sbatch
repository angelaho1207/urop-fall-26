#!/bin/bash
# Embedding similarity, steps 3-4: G101-G112 analyses on the embedding neighbours, overlap check, blind name-check items
# (design.md G118-G120). CPU, no API
#SBATCH -p mit_normal
#SBATCH -c 4
#SBATCH --mem=24G
#SBATCH -t 3:00:00
#SBATCH -J exp2_embed_analyses
#SBATCH -o /orcd/home/002/angela_h/urop-fall-26/logs/exp2_embed_analyses_%j.out
#SBATCH --chdir=/orcd/home/002/angela_h/urop-fall-26/exp2_rollout_gap
#SBATCH --mail-user=angelaho1207@gmail.com
#SBATCH --mail-type=END,FAIL
set -euo pipefail
echo "start: $(date) $(hostname)"
module load miniforge/25.11.0-0
source ~/venvs/cg/bin/activate
python -u s32_concept_similarity.py embed
python -u s33_concept_clusters.py embed
python -u s35_concept_tree.py embed
python -u s39_embed_checks.py
cd .. && git add exp2_rollout_gap/results/full_post_embed_*
git commit -m "Exp 2 embedding similarity: windows, vectors, neighbour analyses and checks (G114-G120)" && git pull --rebase --quiet && git push --quiet
echo "end: $(date)"

#!/bin/bash
# Concept tree: repeated splitting of the top-11 decoder-neighbour graph, where under and over concepts concentrate (design.md G110-G112). CPU, no API
#SBATCH -p mit_normal
#SBATCH -c 2
#SBATCH --mem=8G
#SBATCH -t 1:30:00
#SBATCH -J exp2_tree
#SBATCH --chdir=/orcd/home/002/angela_h/urop-fall-26/exp2_rollout_gap
#SBATCH -o /orcd/home/002/angela_h/urop-fall-26/logs/exp2_tree_%j.out
#SBATCH --mail-user=angelaho1207@gmail.com
#SBATCH --mail-type=END,FAIL
set -euo pipefail
echo "start: $(date) $(hostname)"
module load miniforge/25.11.0-0
source ~/venvs/cg/bin/activate
python -u s35_concept_tree.py
cd .. && git add exp2_rollout_gap/results/full_post_tree_summary.json exp2_rollout_gap/results/full_post_tree_summary.md
git commit -m "Exp 2 concept tree: groups per depth and enrichment results (G110-G112)" && git pull --rebase --quiet && git push --quiet
echo "end: $(date)"

#!/bin/bash
# Concept clusters: spectral clustering of the top-11 decoder-neighbour graph, class concentration test (design.md G105-G108). CPU, no API
#SBATCH -p mit_normal
#SBATCH -c 2
#SBATCH --mem=8G
#SBATCH -t 0:45:00
#SBATCH -J exp2_clusters
#SBATCH --chdir=/orcd/home/002/angela_h/urop-fall-26/exp2_rollout_gap
#SBATCH -o /orcd/home/002/angela_h/urop-fall-26/logs/exp2_clusters_%j.out
#SBATCH --mail-user=angelaho1207@gmail.com
#SBATCH --mail-type=END,FAIL
set -euo pipefail
echo "start: $(date) $(hostname)"
module load miniforge/25.11.0-0
source ~/venvs/cg/bin/activate
python -u s33_concept_clusters.py
cd .. && git add exp2_rollout_gap/results/full_post_clusters_summary.json exp2_rollout_gap/results/full_post_clusters_summary.md
git commit -m "Exp 2 concept clusters: spectral clusters and class concentration results (G105-G108)" && git pull --rebase --quiet && git push --quiet
echo "end: $(date)"

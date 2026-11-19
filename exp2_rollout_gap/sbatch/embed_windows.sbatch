#!/bin/bash
# Embedding similarity, step 1: top-40 Dolma train windows per concept (design.md G114-G116). CPU, no API
#SBATCH -p mit_normal
#SBATCH -c 4
#SBATCH --mem=48G
#SBATCH -t 2:00:00
#SBATCH -J exp2_embed_windows
#SBATCH -o /orcd/home/002/angela_h/urop-fall-26/logs/exp2_embed_windows_%j.out
#SBATCH --chdir=/orcd/home/002/angela_h/urop-fall-26/exp2_rollout_gap
#SBATCH --mail-user=angelaho1207@gmail.com
#SBATCH --mail-type=END,FAIL
set -euo pipefail
echo "start: $(date) $(hostname)"
module load miniforge/25.11.0-0
source ~/venvs/cg/bin/activate
python -u s37_embed_windows.py
echo "end: $(date)"

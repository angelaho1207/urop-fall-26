#!/bin/bash
# Rollouts tab layout: rebuild the names data without cost fields, run the guarded upload, push its check file (design.md G79-G84)
#SBATCH -c 1
#SBATCH --mem=4G
#SBATCH -t 0:15:00
#SBATCH -J exp2_space_tidy
#SBATCH --chdir=/orcd/home/002/angela_h/urop-fall-26/exp2_rollout_gap
#SBATCH -o /orcd/home/002/angela_h/urop-fall-26/logs/exp2_space_tidy_%j.out
#SBATCH --mail-user=angelaho1207@gmail.com
#SBATCH --mail-type=END,FAIL
set -euo pipefail
echo "start: $(date) $(hostname)"
module load miniforge/25.11.0-0
source ~/venvs/cg/bin/activate
mkdir -p ../space/data
python -u s23_space_named.py
python -u s25_space_tidy_upload.py upload
git add results/full_post_space_tidy_check.json
git commit -m "Space: rollouts tab layout live, upload check (G84)"
git pull --rebase --quiet && git push --quiet
echo "end: $(date)"

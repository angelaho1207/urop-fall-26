#!/bin/bash
# Reruns only the G37 Space upload (s08) after finisher_post 27521192 failed there with a 401 (no token under HF_HOME).
#SBATCH -p mit_normal
#SBATCH -c 1
#SBATCH --mem=4G
#SBATCH -t 0:30:00
#SBATCH -J exp2_upload_post
#SBATCH --chdir=/orcd/home/002/angela_h/urop-fall-26/exp2_rollout_gap
#SBATCH -o /orcd/home/002/angela_h/urop-fall-26/logs/exp2_upload_post_%j.out
#SBATCH --mail-user=angelaho1207@gmail.com
#SBATCH --mail-type=END,FAIL
set -euo pipefail
module load miniforge/25.11.0-0
source ~/venvs/cg/bin/activate
python -u s08_space_upload.py

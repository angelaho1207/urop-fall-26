#!/bin/bash
# Names per model and class: selection, check draw, windows (design.md G62-G64). CPU only, no API
#SBATCH -c 4
#SBATCH --mem=48G
#SBATCH -t 3:00:00
#SBATCH -J exp2_named_windows
#SBATCH --requeue
#SBATCH --chdir=/orcd/home/002/angela_h/urop-fall-26/exp2_rollout_gap
#SBATCH -o /orcd/home/002/angela_h/urop-fall-26/logs/exp2_named_windows_%j.out
#SBATCH --mail-user=angelaho1207@gmail.com
#SBATCH --mail-type=END,FAIL
set -euo pipefail
source sbatch/dedupe.sh
dedupe
echo "start: $(date) $(hostname) $SLURM_JOB_PARTITION"
module load miniforge/25.11.0-0
source ~/venvs/cg/bin/activate
python -u s19_named_select.py
cd ../exp1_concept_coverage
python -u s06_examples.py --run full --concepts exp2_named --naming-subsets T1 --quiz-subsets V --out-name examples_named
echo "end: $(date)"

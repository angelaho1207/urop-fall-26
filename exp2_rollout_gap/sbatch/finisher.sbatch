#!/bin/bash
# Waits until every rollout part of both generators is generated and encoded (design.md G21), then runs the
# analysis (s03, G9-G17, loop threshold G14), examples (s04, G19-G20), Space data (s05), the figures (G23), and
# uploads the Space (G24).
#SBATCH -p mit_normal
#SBATCH -c 4
#SBATCH --mem=48G
#SBATCH -t 12:00:00
#SBATCH -J exp2_finish
#SBATCH --chdir=/orcd/home/002/angela_h/urop-fall-26/exp2_rollout_gap
#SBATCH -o /orcd/home/002/angela_h/urop-fall-26/logs/exp2_finisher_%j.out
#SBATCH --mail-user=angelaho1207@gmail.com
#SBATCH --mail-type=END,FAIL

set -euo pipefail
D=/orcd/pool/005/angela_h/exp2/full
done_count() { ls $D/stage1/$1/part_?????.$2 $D/main/$1/part_?????.$2 2>/dev/null | wc -l; }
echo "start: $(date)"
until [ "$(done_count rollouts parquet)" -eq 40 ] && [ "$(done_count acts npz)" -eq 40 ]; do
  # G21: if parts are missing and no worker is queued or running (tunnel worker included), start one
  if [ -z "$(squeue -u angela_h -n exp2_worker -h)" ] && ! pgrep -u angela_h -f worker.sbatch >/dev/null; then
    echo "no worker left, submitting one: $(date)"
    sbatch -p mit_preemptable --gres=gpu:h100:1 sbatch/worker.sbatch
  fi
  sleep 300
done
echo "all parts done: $(date)"
module load miniforge/25.11.0-0
source ~/venvs/cg/bin/activate
python -u s03_distribution.py --run full --degen 0.6
python -u s04_examples.py --run full
python -u s05_space.py --run full
deactivate
# G23: graphs 1-3 and the ratio panel per generator and frame, plus GIFs; into the repo and the Space folder
(cd figures && python make_rollout_figure.py --run full) 2>&1 | grep -v findfont
mkdir -p ../space/data/exp2 && cp figures/full_*.png figures/full_*.gif ../space/data/exp2/
# G24: deploy the Space (tab "Temp visualizations")
~/venvs/cg/bin/hf upload angelaho1207/olmo3-concept-coverage ../space . --repo-type=space \
  --commit-message "Exp 2: Temp visualizations tab with full-run results"
echo "end: $(date)"

#!/bin/bash
# full_post finisher (design.md G21, G26, G33-G37): waits until sft, dpo, instruct are generated and main, sft, dpo,
# instruct are encoded, resubmitting a worker when none is left; then s03 for full_post and full_fimcheck, the G35
# check, examples, Space data, figures, and the Space upload with its hash check.
# Copies may be queued on several partitions; the lowest-id running copy goes on and cancels the others (G26).
#SBATCH -c 4
#SBATCH --mem=128G
#SBATCH -t 12:00:00
#SBATCH -J exp2_finish_post
#SBATCH --requeue
#SBATCH --chdir=/orcd/home/002/angela_h/urop-fall-26/exp2_rollout_gap
#SBATCH -o /orcd/home/002/angela_h/urop-fall-26/logs/exp2_finisher_post_%j.out
#SBATCH --mail-user=angelaho1207@gmail.com
#SBATCH --mail-type=END,FAIL

set -euo pipefail
D=/orcd/pool/005/angela_h/exp2/full_post
count() { ls $(for g in $1; do echo $D/$g/$2/part_?????.$3; done) 2>/dev/null | wc -l; }
echo "start: $(date)"
others=$(squeue -u angela_h -h -n exp2_finish_post -o "%i %T" | awk -v me="$SLURM_JOB_ID" '$1 != me')
if echo "$others" | awk -v me="$SLURM_JOB_ID" '$2 == "RUNNING" && $1 < me' | grep -q .; then
  echo "an earlier finisher is running, exiting"; exit 0
fi
for job_id in $(echo "$others" | awk '{print $1}'); do scancel "$job_id"; done
until [ "$(count 'sft dpo instruct' rollouts parquet)" -eq 60 ] && [ "$(count 'main sft dpo instruct' acts npz)" -eq 80 ]; do
  # G21: if parts are missing and no worker is queued or running, start one
  if [ -z "$(squeue -u angela_h -n exp2_worker_post -h)" ]; then
    echo "no worker left, submitting one: $(date)"
    sbatch -p mit_preemptable --gres=gpu:1 -t 6:00:00 sbatch/worker_post.sbatch
  fi
  sleep 300
done
echo "all parts done: $(date)"
module load miniforge/25.11.0-0
source ~/venvs/cg/bin/activate
python -u s03_distribution.py --run full_post --degen 0.6
python -u s03_distribution.py --run full_fimcheck --degen 0.6  # G35
python -u s07_fimcheck.py
python -u s04_examples.py --run full_post
python -u s05_space.py --run full_post --generators sft dpo instruct
deactivate  # matplotlib is in the miniforge base env, not in ~/venvs/cg (as finisher.sbatch)
# G23, G28, G37: figures for the three post-trained generators, into the repo and the Space folder
(cd figures && python make_rollout_figure.py --run full_post --generators sft dpo instruct) 2>&1 | { grep -v findfont || true; }
(cd figures && python make_histograms.py --run full_post --generators sft dpo instruct) 2>&1 | { grep -v findfont || true; }
mkdir -p ../space/data/exp2 && cp figures/full_post_*.png figures/full_post_*.gif ../space/data/exp2/
source ~/venvs/cg/bin/activate
python -u s08_space_upload.py  # G37: added-lines check, hash check before and after
echo "end: $(date)"

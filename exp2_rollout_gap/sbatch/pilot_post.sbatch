#!/bin/bash
# Pilot for the post-trained generators (design.md G30-G36): 200 rollouts each, encoding, s03, and the G36 report.
# If the G36 gate passes, it submits the full run (sbatch/launch_full_post.sh, G38); if not, the job fails (mail).
# Copies may be queued on several partitions (as G26); the lowest-id running copy goes on and cancels the others.
#   sbatch -p mit_normal_gpu --gres=gpu:1 sbatch/pilot_post.sbatch
#SBATCH -c 8
#SBATCH --mem=64G
#SBATCH -t 02:00:00
#SBATCH -J exp2_pilot_post
#SBATCH --requeue
#SBATCH --chdir=/orcd/home/002/angela_h/urop-fall-26/exp2_rollout_gap
#SBATCH -o /orcd/home/002/angela_h/urop-fall-26/logs/exp2_pilot_post_%j.out
#SBATCH --mail-user=angelaho1207@gmail.com
#SBATCH --mail-type=END,FAIL

set -uo pipefail
echo "host: $(hostname)  job: $SLURM_JOB_ID  partition: $SLURM_JOB_PARTITION  gpu: $(nvidia-smi --query-gpu=name --format=csv,noheader)  start: $(date)"
others=$(squeue -u angela_h -h -n exp2_pilot_post -o "%i %T" | awk -v me="$SLURM_JOB_ID" '$1 != me')
if echo "$others" | awk -v me="$SLURM_JOB_ID" '$2 == "RUNNING" && $1 < me' | grep -q .; then
  echo "an earlier copy is running, exiting"; exit 0
fi
for job_id in $(echo "$others" | awk '{print $1}'); do scancel "$job_id"; done
module load miniforge/25.11.0-0
source ~/venvs/cg/bin/activate
set -e
for g in sft dpo instruct; do python -u s01_rollouts.py --run pilot_post --generator $g --n 200 2>&1 | grep --line-buffered -v CUDACachingAllocator; done
for g in sft dpo instruct; do python -u s02_activations.py --run pilot_post --generator $g; done
python -u s03_distribution.py --run pilot_post --degen 0.6
set +e
python -u s06_post_report.py
gate=$?
echo "report exit code: $gate"
if [ "$gate" -ne 0 ]; then echo "G36 gate failed or report error, full run not submitted"; exit 3; fi
[ -e /orcd/pool/005/angela_h/exp2/full_post/.launched ] && { echo "full run already launched"; exit 0; }
touch /orcd/pool/005/angela_h/exp2/full_post/.launched  # a requeued copy does not launch twice
bash sbatch/launch_full_post.sh
echo "end: $(date)"

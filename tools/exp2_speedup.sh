#!/bin/bash
# Exp 2 full run (design.md G25): cut pending workers to 2 h so backfill can start them sooner, keep one 2 h worker
# queued on mit_normal_gpu, then report parts done, worker speed and start estimates.
# From the laptop:  ssh -t orcd-login "cd ~/urop-fall-26 && git pull -q --ff-only && bash tools/exp2_speedup.sh"
set -uo pipefail
cd ~/urop-fall-26 || exit 1
WORKER_LIMIT=2:00:00
exp2_data=/orcd/pool/005/angela_h/exp2/full
echo "=== $(date)"

echo "=== parts (20 per generator); lock age in minutes, over 10 = abandoned"
for generator in stage1 main; do
  echo "$generator: $(ls $exp2_data/$generator/rollouts/part_?????.parquet 2>/dev/null | wc -l) generated," \
       "$(ls $exp2_data/$generator/acts/part_?????.npz 2>/dev/null | wc -l) encoded"
  for lock in $exp2_data/$generator/rollouts/*.lock $exp2_data/$generator/acts/*.lock; do
    [ -e "$lock" ] && echo "  $(basename $(dirname $lock))/$(basename $lock): $(( ($(date +%s) - $(stat -c %Y $lock)) / 60 )) min"
  done
done

echo "=== recent part speeds"
grep -h "^part" logs/exp2_worker_*.out 2>/dev/null | tail -n 5

echo "=== pending workers -> $WORKER_LIMIT"
for job_id in $(squeue --me -h -t PD -n exp2_worker -o %i); do
  scontrol update JobId=$job_id TimeLimit=$WORKER_LIMIT && echo "$job_id: TimeLimit=$WORKER_LIMIT"
done

# mit_normal_gpu allows 2 GPUs per user (G21); fill a free slot with a short worker
normal_gpu_jobs=$(squeue --me -h -p mit_normal_gpu -o %i | wc -l)
if [ "$normal_gpu_jobs" -lt 2 ]; then
  sbatch --test-only -p mit_normal_gpu -G 1 -t $WORKER_LIMIT exp2_rollout_gap/sbatch/worker.sbatch
  echo "submitted: $(sbatch --parsable -p mit_normal_gpu -G 1 -t $WORKER_LIMIT exp2_rollout_gap/sbatch/worker.sbatch)"
fi

sleep 60  # let the scheduler re-evaluate before reading estimates
echo "=== queue with start estimates"
squeue --me --start -o "%.10i %.9P %.12j %.2t %.20S %.16b %.8l %r"
echo "=== running"
squeue --me -t R -o "%.10i %.9P %.12j %.10M %.8l %N"
echo "=== idle or partly used GPU nodes"
sinfo -p mit_normal_gpu,mit_preemptable -t idle,mix -o "%P %G %t %D"

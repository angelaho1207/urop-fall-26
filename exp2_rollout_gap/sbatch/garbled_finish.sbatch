#!/bin/bash
# Garbled check finisher (design.md G55-G58): waits for all 120 NLL parts, submitting a worker when parts are missing
# and none is queued or running; then s15. Copies on several partitions; the lowest-id running copy goes on (G26).
#SBATCH -c 4
#SBATCH --mem=128G
#SBATCH -t 10:00:00
#SBATCH -J exp2_garbled_finish
#SBATCH --requeue
#SBATCH --chdir=/orcd/home/002/angela_h/urop-fall-26/exp2_rollout_gap
#SBATCH -o /orcd/home/002/angela_h/urop-fall-26/logs/exp2_garbled_finish_%j.out
#SBATCH --mail-user=angelaho1207@gmail.com
#SBATCH --mail-type=END,FAIL
set -euo pipefail
source sbatch/dedupe.sh
dedupe
echo "start: $(date) $(hostname) $SLURM_JOB_PARTITION"
D=/orcd/pool/005/angela_h/exp2/full_post/nll
until [ "$(ls $D/*/part_?????.npz 2>/dev/null | wc -l)" -eq 120 ]; do
  if [ -z "$(squeue -u angela_h -n exp2_nll_worker -h)" ]; then
    echo "no worker left, submitting one: $(date)"
    sbatch -p mit_preemptable --gres=gpu:1 sbatch/nll_worker.sbatch
  fi
  sleep 300
done
echo "all NLL parts done: $(date)"
module load miniforge/25.11.0-0
source ~/venvs/cg/bin/activate
python -u s15_garbled.py
echo "end: $(date)"

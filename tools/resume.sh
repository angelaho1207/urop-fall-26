#!/bin/bash
# Run after logging back in to ORCD:  bash ~/urop-fall-26/tools/resume.sh        (CPU tunnel)
#                                     bash ~/urop-fall-26/tools/resume.sh gpu    (GPU tunnel)
# Pulls the repo, submits a tunnel job unless one is already queued or running, waits until it runs,
# then prints the tunnel log (with the GitHub device code, if any), the job queue and Exp 2 progress.
set -uo pipefail
cd ~/urop-fall-26 || exit 1
git status --short
git pull --ff-only

tunnel_job=$(squeue --me -h -o %i -n tunnel,tunnel_cpu | head -n 1)
if [ -z "$tunnel_job" ]; then
  tunnel_script=tools/tunnel_cpu.sbatch
  [ "${1:-}" = "gpu" ] && tunnel_script=tools/tunnel.sbatch
  tunnel_job=$(sbatch --parsable "$tunnel_script")
  echo "submitted $tunnel_script as job $tunnel_job"
else
  echo "tunnel job $tunnel_job already in the queue"
fi

# Wait for the job to start; the log file only exists once it runs
until [ "$(squeue -h -j "$tunnel_job" -o %T)" = "RUNNING" ]; do
  job_state=$(squeue -h -j "$tunnel_job" -o "%T %r")
  if [ -z "$job_state" ]; then echo "job $tunnel_job left the queue; see: sacct -j $tunnel_job"; exit 1; fi
  echo "$(date +%H:%M:%S) $job_state"
  sleep 20
done
tunnel_log=logs/$(squeue -h -j "$tunnel_job" -o %j)_$tunnel_job.out
until [ -s "$tunnel_log" ]; do sleep 5; done
sleep 15  # give the VS Code CLI time to print the tunnel link or device code
echo "--- $tunnel_log"
tail -n 15 "$tunnel_log"
echo "--- queue"
squeue --me

exp2_data=/orcd/pool/005/angela_h/exp2/full
if [ -d "$exp2_data" ]; then
  echo "--- Exp 2 parts (20 per generator)"
  for generator in stage1 main; do
    echo "$generator: $(ls $exp2_data/$generator/rollouts/part_?????.parquet 2>/dev/null | wc -l) generated," \
         "$(ls $exp2_data/$generator/acts/part_?????.npz 2>/dev/null | wc -l) encoded," \
         "locked: $(ls $exp2_data/$generator/rollouts/ 2>/dev/null | grep lock | tr '\n' ' ')"
  done
fi
echo "VS Code: Ctrl+Shift+P -> Remote-Tunnels: Connect to Tunnel... -> orcd-cg"

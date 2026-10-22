#!/bin/bash
# Prints Exp 2 job changes every 2 min until the finisher leaves the queue (START/END per job, STATUS each pass).
# From the laptop:  ssh orcd-login "cd ~/urop-fall-26 && git pull -q --ff-only && bash tools/exp2_watch.sh" > watch.log
cd ~/urop-fall-26 || exit 1
exp2_data=/orcd/pool/005/angela_h/exp2/full
declare -A previous_jobs current_jobs
while true; do
  current_jobs=()
  while read -r job_id job_name job_state; do current_jobs[$job_id]="$job_name $job_state"; done < <(squeue --me -h -o "%i %j %T")
  for job_id in "${!current_jobs[@]}"; do
    if [[ ${current_jobs[$job_id]} == *RUNNING && "${previous_jobs[$job_id]:-}" != "${current_jobs[$job_id]}" ]]; then
      echo "START $job_id ${current_jobs[$job_id]} $(date +%H:%M)"
    fi
  done
  for job_id in "${!previous_jobs[@]}"; do
    if [ -z "${current_jobs[$job_id]:-}" ]; then
      echo "END $job_id ${previous_jobs[$job_id]%% *} $(sacct -j $job_id -X -n -o State | tr -d ' ') $(date +%H:%M)"
    fi
  done
  echo "STATUS $(date +%H:%M) workers_running=$(squeue --me -h -t R -n exp2_worker | wc -l)" \
       "main_generated=$(ls $exp2_data/main/rollouts/part_?????.parquet 2>/dev/null | wc -l)/20" \
       "encoded=$(ls $exp2_data/*/acts/part_?????.npz 2>/dev/null | wc -l)/40"
  previous_jobs=()
  for job_id in "${!current_jobs[@]}"; do previous_jobs[$job_id]=${current_jobs[$job_id]}; done
  if [ -z "$(squeue --me -h -n exp2_finish)" ]; then echo "FINISHER_GONE $(date +%H:%M)"; exit 0; fi
  sleep 120
done

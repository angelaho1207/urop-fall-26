# G26, G46: copies of one job wait on several partitions; the lowest-id running copy goes on and cancels the others
dedupe() {
  local others
  others=$(squeue -u angela_h -h -n "$SLURM_JOB_NAME" -o "%i %T" | awk -v me="$SLURM_JOB_ID" '$1 != me')
  if echo "$others" | awk -v me="$SLURM_JOB_ID" '$2 == "RUNNING" && $1 < me' | grep -q .; then
    echo "an earlier copy is running, exiting"; exit 0
  fi
  for job_id in $(echo "$others" | awk '{print $1}'); do scancel "$job_id"; done
}

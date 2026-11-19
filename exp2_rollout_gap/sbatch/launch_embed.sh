#!/bin/bash
# Embedding similarity (design.md G114-G120): windows (CPU) -> vectors (GPU) -> analyses (CPU), each starting when the
# previous one succeeds. If the GPU job hits its time limit, the analyses job is cancelled: resubmit
# embed_vectors.sbatch (it resumes), then embed_analyses.sbatch.
set -euo pipefail
cd /orcd/home/002/angela_h/urop-fall-26/exp2_rollout_gap
j1=$(sbatch --parsable sbatch/embed_windows.sbatch)
j2=$(sbatch --parsable --dependency=afterok:$j1 sbatch/embed_vectors.sbatch)
j3=$(sbatch --parsable --dependency=afterok:$j2 sbatch/embed_analyses.sbatch)
echo "windows $j1, vectors $j2, analyses $j3"

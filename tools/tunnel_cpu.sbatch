#!/bin/bash
# VS Code tunnel on a CPU node, for steps that need no GPU (s06-s09, website, analysis).
# Same tunnel name as tunnel.sbatch, so VS Code reconnects to "orcd-cg". Run only one tunnel job at a time.
# Set -t so the job ends before any maintenance window (Slurm will not start a job that overlaps one).
#SBATCH -p mit_normal
#SBATCH -c 8
#SBATCH --mem=64G
#SBATCH -t 12:00:00
#SBATCH -J tunnel_cpu
#SBATCH --chdir=/home/angela_h/urop-fall-26
#SBATCH -o logs/tunnel_cpu_%j.out

echo "host: $(hostname)  job: $SLURM_JOB_ID  start: $(date)"
module load miniforge/25.11.0-0
source ~/venvs/cg/bin/activate
~/bin/code tunnel --accept-server-license-terms --name orcd-cg

#!/bin/bash
# VS Code tunnel on a GPU compute node. Submit with: sbatch tools/tunnel.sbatch
#SBATCH -p mit_normal_gpu
#SBATCH -G 1
#SBATCH -c 8
#SBATCH --mem=64G
#SBATCH -t 06:00:00
#SBATCH -J tunnel
#SBATCH --chdir=/home/angela_h/urop-fall-26
#SBATCH -o logs/tunnel_%j.out

echo "host: $(hostname)  job: $SLURM_JOB_ID  gpus: $CUDA_VISIBLE_DEVICES  start: $(date)"
module load miniforge/25.11.0-0
source ~/venvs/cg/bin/activate
~/bin/code tunnel --accept-server-license-terms --name orcd-cg

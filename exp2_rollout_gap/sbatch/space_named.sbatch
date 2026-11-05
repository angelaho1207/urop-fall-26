#!/bin/bash
# Space rearranged, names results: data, static checks, headless browser test (design.md G75-G77). STAGE=upload uploads instead
#SBATCH -c 2
#SBATCH --mem=8G
#SBATCH -t 0:15:00
#SBATCH -J exp2_space_named
#SBATCH --chdir=/orcd/home/002/angela_h/urop-fall-26/exp2_rollout_gap
#SBATCH -o /orcd/home/002/angela_h/urop-fall-26/logs/exp2_space_named_%j.out
#SBATCH --mail-user=angelaho1207@gmail.com
#SBATCH --mail-type=FAIL
set -euo pipefail
echo "start: $(date) $(hostname) ${STAGE:-check}"
module load miniforge/25.11.0-0
source ~/venvs/cg/bin/activate
if [ "${STAGE:-check}" = "upload" ]; then
  python -u s24_space_named_upload.py upload
else
  python -u s23_space_named.py
  deactivate
  PW=/orcd/pool/005/angela_h/tools/pw_venv
  export PLAYWRIGHT_BROWSERS_PATH=/orcd/pool/005/angela_h/tools/pw_browsers
  if [ ! -x "$PW/bin/playwright" ]; then python -m venv "$PW" && "$PW/bin/pip" install -q playwright; fi
  "$PW/bin/playwright" install chromium 2>&1 | tail -2
  "$PW/bin/python" -u s24_space_named_upload.py check
fi
echo "end: $(date)"

#!/bin/bash
# Names per model: selection, check draw, windows, free check, then the rest of the chain (design.md G70-G73). No paid call
#SBATCH -c 4
#SBATCH --mem=48G
#SBATCH -t 3:00:00
#SBATCH -J exp2_named_windows
#SBATCH --requeue
#SBATCH --chdir=/orcd/home/002/angela_h/urop-fall-26/exp2_rollout_gap
#SBATCH -o /orcd/home/002/angela_h/urop-fall-26/logs/exp2_named_windows_%j.out
#SBATCH --mail-user=angelaho1207@gmail.com
#SBATCH --mail-type=END,FAIL
set -euo pipefail
source sbatch/dedupe.sh
dedupe
echo "start: $(date) $(hostname) $SLURM_JOB_PARTITION"
timeout 30 git ls-remote origin HEAD && echo "github reachable" || echo "github NOT reachable from this node"
module load miniforge/25.11.0-0
source ~/venvs/cg/bin/activate
python -u s19_named_select.py
LIST=/orcd/pool/005/angela_h/exp2/full_post/named/t1_concepts.json
if python -c "import json,sys; sys.exit(0 if json.load(open('$LIST')) else 1)"; then
  (cd ../exp1_concept_coverage && python -u s06_examples.py --run full --concepts exp2_named --naming-subsets T1 --quiz-subsets "" --out-name examples_named)
fi
python -u s20_named_labels.py check   # a failed check stops the chain here, before any money moves
MARK=/orcd/pool/005/angela_h/exp2/full_post/named/chain_ids.txt
if [ -f "$MARK" ]; then echo "chain already submitted: $(cat "$MARK")"; exit 0; fi
l1=$(sbatch --parsable -p mit_normal sbatch/named_labels.sbatch)
l2=$(sbatch --parsable -p mit_preemptable sbatch/named_labels.sbatch)
n1=$(sbatch --parsable -p mit_normal sbatch/named_noise.sbatch)
n2=$(sbatch --parsable -p mit_preemptable sbatch/named_noise.sbatch)
f=$(sbatch --parsable -p mit_normal --dependency=afterany:$l1:$l2:$n1:$n2 sbatch/named_finish.sbatch)
echo "labels $l1 $l2 noise $n1 $n2 finish $f" | tee "$MARK"
echo "end: $(date)"

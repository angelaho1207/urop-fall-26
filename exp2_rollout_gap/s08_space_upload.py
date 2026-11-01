"""Upload the post-trained section to the Space without changing any existing file (design.md G37).

Usage: python s08_space_upload.py
1. `git diff 4764b71` of space/app.js, index.html and style.css must show added lines only.
2. Lists every remote file with its hash (LFS sha256 or git blob id) before the upload.
3. Uploads only data/rollouts_post.json, data/exp2/full_post_*, app.js, index.html, style.css; every uploaded data
   path must be new on the remote.
4. Lists the remote again; every file present before, other than the three allowed ones, must keep its hash.
Writes results/full_post_space_check.json. Exit code 1 if any check fails (no upload happens if 1-3 fail).
"""
import json
import subprocess
import sys
from pathlib import Path

import settings
from huggingface_hub import HfApi

REPO = "angelaho1207/olmo3-concept-coverage"
SPACE = settings.RESULTS.parent.parent / "space"
BASE_COMMIT = "4764b71"  # last commit before the post-trained section
ALLOWED = ["app.js", "index.html", "style.css"]
NEW = ["data/rollouts_post.json", "data/exp2/full_post_*"]
N_FIGURES = 3 * 12  # per generator: 5 rank PNGs + GIF, 5 histogram PNGs + GIF
# Exp 1 config moves HF_HOME to the pool cache, which holds no login token; read the token from the default location
TOKEN_FILE = Path.home() / ".cache" / "huggingface" / "token"


def snapshot(api):
    info = api.space_info(REPO, files_metadata=True)
    return info.sha, {s.rfilename: (s.lfs.sha256 if s.lfs else s.blob_id) for s in info.siblings}


def main():
    out = settings.RESULTS / "full_post_space_check.json"
    report = {"repo": REPO, "uploaded_patterns": ALLOWED + NEW}

    def stop(reason):
        report["result"] = "stopped: " + reason
        out.write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=1))
        sys.exit(1)

    diff = subprocess.run(["git", "diff", BASE_COMMIT, "--"] + [f"space/{f}" for f in ALLOWED], cwd=SPACE.parent,
                          capture_output=True, text=True, check=True).stdout
    removed = [line for line in diff.splitlines() if line.startswith("-") and not line.startswith("---")]
    report["git_diff_removed_lines"] = len(removed)
    if removed:
        stop(f"git diff {BASE_COMMIT} shows {len(removed)} removed or changed lines in {ALLOWED}")

    figures = sorted(p.relative_to(SPACE).as_posix() for p in (SPACE / "data" / "exp2").glob("full_post_*"))
    report["local_new_files"] = len(figures) + 1
    if not (SPACE / "data" / "rollouts_post.json").exists() or len(figures) != N_FIGURES:
        stop(f"expected rollouts_post.json and {N_FIGURES} figures, found {len(figures)} figures")

    api = HfApi(token=TOKEN_FILE.read_text().strip())
    sha_before, before = snapshot(api)
    report["before"] = {"commit": sha_before, "files": len(before)}
    clash = [f for f in figures + ["data/rollouts_post.json"] if f in before]
    if clash:
        stop(f"{len(clash)} new paths already exist on the remote: {clash[:5]}")

    commit = api.upload_folder(folder_path=str(SPACE), repo_id=REPO, repo_type="space", allow_patterns=ALLOWED + NEW,
                               commit_message="Exp 2: post-trained generators section in Temp visualizations (G37)")
    sha_after, after = snapshot(api)
    changed = sorted(f for f in before if f in after and before[f] != after[f])
    report["after"] = {"commit": sha_after, "files": len(after), "upload_commit": str(commit)}
    report["changed_existing"] = changed
    report["removed"] = sorted(f for f in before if f not in after)
    report["added"] = sorted(f for f in after if f not in before)
    bad = [f for f in changed if f not in ALLOWED] + report["removed"]
    report["result"] = "ok" if not bad else f"existing files changed or removed: {bad}"
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "added"}, indent=1), f"\nadded {len(report['added'])} files")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

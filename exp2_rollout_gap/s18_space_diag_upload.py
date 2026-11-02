"""Upload the "Exp 2 diagnostics" section to the Space without changing any existing file (design.md G61; s08 style).

Usage: python s18_space_diag_upload.py   (after s17_space_diag.py)
Before the upload (any failure stops it):
1. `git diff 5ff5805` of space/app.js, index.html and style.css shows added lines only.
2. The remote copies of these three files equal their 5ff5805 versions (git blob id), so no remote edit is overwritten.
3. The 13 new paths (data/exp2_diagnostics.json and 12 PNGs) exist locally and none exists on the remote.
Upload: only the 13 new paths and the three code files. After the upload:
4. Every file present before, other than the three code files and .gitattributes, keeps its hash; nothing is removed.
5. .gitattributes only gains lines, and each added line names one of the new paths.
6. Each new path's remote hash (LFS sha256 or git blob id) equals the local file's.
Writes results/full_post_space_diag_check.json. Exit code 1 if any check fails.
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import settings
from huggingface_hub import HfApi, hf_hub_download

from s17_space_diag import SETS

REPO = "angelaho1207/olmo3-concept-coverage"
SPACE = Path(__file__).resolve().parent.parent / "space"
BASE_COMMIT = "5ff5805"  # last commit before the diagnostics section
CODE = ["app.js", "index.html", "style.css"]
NEW = ["data/exp2_diagnostics.json"] + [f"data/exp2/full_post_{s}_{k}.png" for s in SETS for k in ("scatter", "hist_shifted")]
# Exp 1 config moves HF_HOME to the pool cache, which holds no login token; read the token from the default location
TOKEN_FILE = Path.home() / ".cache" / "huggingface" / "token"


def git_blob(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def local_hashes(data):
    return {git_blob(data), hashlib.sha256(data).hexdigest()}


def snapshot(api):
    info = api.space_info(REPO, files_metadata=True)
    return info.sha, {s.rfilename: (s.lfs.sha256 if s.lfs else s.blob_id) for s in info.siblings}


def gitattributes(api, revision):
    path = hf_hub_download(REPO, ".gitattributes", repo_type="space", revision=revision, token=api.token,
                           cache_dir=settings.DATA / "hf_space_check")
    return Path(path).read_text().splitlines()


def main():
    out = settings.RESULTS / "full_post_space_diag_check.json"
    report = {"repo": REPO, "base_commit": BASE_COMMIT, "uploaded": CODE + NEW}

    def stop(reason):
        report["result"] = "stopped: " + reason
        out.write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=1))
        sys.exit(1)

    # 1
    diff = subprocess.run(["git", "diff", BASE_COMMIT, "--"] + [f"space/{f}" for f in CODE], cwd=SPACE.parent,
                          capture_output=True, text=True, check=True).stdout
    removed = [line for line in diff.splitlines() if line.startswith("-") and not line.startswith("---")]
    report["git_diff_added_lines"] = sum(1 for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++"))
    report["git_diff_removed_lines"] = len(removed)
    if removed:
        stop(f"git diff {BASE_COMMIT} shows {len(removed)} removed or changed lines in {CODE}")
    missing = [f for f in NEW if not (SPACE / f).exists()]
    if missing:
        stop(f"run s17_space_diag.py first; missing {missing}")

    api = HfApi(token=TOKEN_FILE.read_text().strip())
    sha_before, before = snapshot(api)
    report["before"] = {"commit": sha_before, "files": len(before)}
    # 2
    base_blobs = {f: git_blob(subprocess.run(["git", "show", f"{BASE_COMMIT}:space/{f}"], cwd=SPACE.parent,
                                             capture_output=True, check=True).stdout) for f in CODE}
    edited = [f for f in CODE if before.get(f) != base_blobs[f]]
    if edited:
        stop(f"remote {edited} differ from their {BASE_COMMIT} versions")
    # 3
    clash = [f for f in NEW if f in before]
    if clash:
        stop(f"{len(clash)} new paths already exist on the remote: {clash}")
    attrs_before = gitattributes(api, sha_before)

    commit = api.upload_folder(folder_path=str(SPACE), repo_id=REPO, repo_type="space", allow_patterns=CODE + NEW,
                               commit_message="Exp 2 diagnostics section in Temp visualizations (G61)")
    sha_after, after = snapshot(api)
    report["after"] = {"commit": sha_after, "files": len(after), "upload_commit": str(commit)}
    # 4
    changed = sorted(f for f in before if f in after and before[f] != after[f])
    report["changed_existing"] = changed
    report["removed"] = sorted(f for f in before if f not in after)
    report["added"] = sorted(f for f in after if f not in before)
    bad = [f"changed: {f}" for f in changed if f not in CODE + [".gitattributes"]] + [f"removed: {f}" for f in report["removed"]]
    # 5
    attrs_after = gitattributes(api, sha_after)
    added_attr = attrs_after[len(attrs_before):]
    report["gitattributes_added_lines"] = added_attr
    if attrs_after[:len(attrs_before)] != attrs_before:
        bad.append(".gitattributes: existing lines changed")
    bad += [f".gitattributes: added line {line!r} names no new path" for line in added_attr if line.split(" ")[0] not in NEW]
    # 6
    for f in CODE + NEW:
        if after.get(f) not in local_hashes((SPACE / f).read_bytes()):
            bad.append(f"remote {f} differs from the local file")
    if sorted(report["added"]) != sorted(NEW):
        bad.append(f"added paths {report['added']} are not the 13 new paths")
    report["result"] = "ok" if not bad else f"failed: {bad}"
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=1))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

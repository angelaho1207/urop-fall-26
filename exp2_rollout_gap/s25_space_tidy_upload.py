"""Check the rollouts tab layout (G79-G83), and upload it (design.md G84; s24 style).

Usage: python s25_space_tidy_upload.py check    # static checks only; Claude ran the browser test before commit
       python s25_space_tidy_upload.py upload   # after s23: guarded upload, hash checks, writes results/full_post_space_tidy_check.json
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPACE = HERE.parent / "space"
RESULTS = HERE / "results"
REPO = "angelaho1207/olmo3-concept-coverage"
BASE_COMMIT = "ad2ff58"  # last commit with the code as uploaded (G78)
CODE = ["app.js", "index.html", "style.css"]
DATA = "data/exp2_named.json"
REMOVED_KEYS = {"spent_usd", "limit_usd", "usage", "check"}  # G83: the only keys this change takes out of the data file
SOURCE_KEY = "sources"  # lists input files, so it changes with the removal of the check file
COST_TEXT = re.compile(r"spent_usd|limit_usd|d\.usage|Cost by|Spent \$|\bUSD\b")
TOKEN_FILE = Path.home() / ".cache" / "huggingface" / "token"


def show(path):
    return subprocess.run(["git", "show", f"{BASE_COMMIT}:space/{path}"], cwd=SPACE.parent, capture_output=True, check=True).stdout


def static_checks():
    bad = []
    html, js, css = (SPACE / "index.html").read_text(encoding="utf-8"), (SPACE / "app.js").read_text(encoding="utf-8"), (SPACE / "style.css").read_text(encoding="utf-8")
    ids = set(re.findall(r'id="([^"]+)"', html))
    lost = set(re.findall(r'id="([^"]+)"', show("index.html").decode("utf-8"))) - ids
    if lost:
        bad.append(f"element ids lost: {sorted(lost)}")
    absent = set(re.findall(r'getElementById\("([^"]+)"\)', js)) - ids - {"topic-line"}  # topic-line is made by the script on concept pages
    if absent:
        bad.append(f"ids the script looks up that the page does not hold: {sorted(absent)}")
    for hash_ in re.findall(r'href="#([^"]+)"', html + js):
        if "$" not in hash_ and "=" not in hash_ and f"tab-{hash_}" not in ids and f"sec-{hash_}" not in ids:
            bad.append(f"link #{hash_} leads nowhere")
    plots = set(re.findall(r'Plotly\.(?:newPlot|react)\("([^"]+)"', js)) - ids
    if plots:
        bad.append(f"plots without a div: {sorted(plots)}")
    lazy = set(re.findall(r'"(sec-[-\w]+)":', js)) - ids
    if lazy:
        bad.append(f"dropdowns the script draws that the page does not hold: {sorted(lazy)}")
    for hit in COST_TEXT.findall(html + js):
        bad.append(f"cost text on the page: {hit}")
    if "keymark" in html + js + css or "keyrow" in html + js + css:
        bad.append("stars or key rows remain")
    if "Dolma vs Pile (web text only) (OLD)" not in html:
        bad.append("first tab not renamed")
    named = json.loads((SPACE / DATA).read_text(encoding="utf-8")) if (SPACE / DATA).exists() else None
    if named is None:
        bad.append(f"run s23_space_named.py first; missing {DATA}")
    elif REMOVED_KEYS & set(named):
        bad.append(f"cost keys remain in the data file: {sorted(REMOVED_KEYS & set(named))}")
    return bad


def git_blob(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def snapshot(api):
    info = api.space_info(REPO, files_metadata=True)
    return info.sha, {s.rfilename: (s.lfs.sha256 if s.lfs else s.blob_id) for s in info.siblings}


def upload():
    from huggingface_hub import HfApi, hf_hub_download
    out = RESULTS / "full_post_space_tidy_check.json"
    uploaded = CODE + [DATA]
    report = {"repo": REPO, "base_commit": BASE_COMMIT, "uploaded": uploaded}

    def stop(reason):
        report["result"] = "stopped: " + reason
        out.write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=1))
        sys.exit(1)

    bad = static_checks()
    if bad:
        stop(f"static checks: {bad}")
    api = HfApi(token=TOKEN_FILE.read_text().strip())
    sha_before, before = snapshot(api)
    report["before"] = {"commit": sha_before, "files": len(before)}
    edited = [f for f in CODE if before.get(f) != git_blob(show(f))]
    if edited:
        stop(f"remote {edited} differ from their {BASE_COMMIT} versions")

    # G84: the new data file may differ from the remote one only by the removed keys
    remote_path = hf_hub_download(REPO, DATA, repo_type="space", revision=sha_before, token=api.token, cache_dir="/orcd/pool/005/angela_h/exp2/hf_space_check")
    remote, local = json.loads(Path(remote_path).read_text(encoding="utf-8")), json.loads((SPACE / DATA).read_text(encoding="utf-8"))
    if set(remote) - set(local) != REMOVED_KEYS or set(local) - set(remote):
        stop(f"data keys differ: removed {sorted(set(remote) - set(local))}, added {sorted(set(local) - set(remote))}")
    moved = [k for k in local if k != SOURCE_KEY and local[k] != remote[k]]
    if moved:
        stop(f"data values changed: {moved}")

    commit = api.upload_folder(folder_path=str(SPACE), repo_id=REPO, repo_type="space", allow_patterns=uploaded,
                               commit_message="Rollouts tab: key results visible, details in dropdowns, one-sentence names, no costs; first tab marked OLD (G79-G84)")
    sha_after, after = snapshot(api)
    report["after"] = {"commit": sha_after, "files": len(after), "upload_commit": str(commit)}
    changed = sorted(f for f in before if f in after and before[f] != after[f])
    report.update(changed_existing=changed, removed=sorted(f for f in before if f not in after), added=sorted(f for f in after if f not in before))
    bad = [f"changed: {f}" for f in changed if f not in uploaded + [".gitattributes"]] + [f"removed: {f}" for f in report["removed"]] + [f"added: {f}" for f in report["added"]]
    for f in uploaded:
        data = (SPACE / f).read_bytes()
        if after.get(f) not in {git_blob(data), hashlib.sha256(data).hexdigest()}:
            bad.append(f"remote {f} differs from the local file")
    report["result"] = "ok" if not bad else f"failed: {bad}"
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=1))
    sys.exit(1 if bad else 0)


def check():
    bad = static_checks()
    print("static:", bad or "ok", flush=True)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["check", "upload"])
    {"check": check, "upload": upload}[parser.parse_args().stage]()

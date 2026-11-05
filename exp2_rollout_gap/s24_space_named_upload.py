"""Check the rearranged Space, and upload it (design.md G77; s18 style).

Usage: python s24_space_named_upload.py check    # static checks and a headless browser test; no upload
       python s24_space_named_upload.py upload   # after check: guarded upload, hash checks, writes results/full_post_space_named_check.json
The browser test needs Playwright (its own venv on pool, see sbatch/space_named.sbatch).
"""
import argparse
import functools
import hashlib
import http.server
import json
import re
import subprocess
import sys
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPACE = HERE.parent / "space"
RESULTS = HERE / "results"
REPO = "angelaho1207/olmo3-concept-coverage"
BASE_COMMIT = "dec0e3a"  # last commit with the code as uploaded (G75-G77, Space commit b9646599)
CODE = ["app.js", "index.html", "style.css"]
NEW = []  # G78: the data files are already on the Space and do not change
OLD_TABS = {"sec-key", "named-key"}  # G78: the only ids this change removes
TOKEN_FILE = Path.home() / ".cache" / "huggingface" / "token"
SHOTS = Path("/orcd/pool/005/angela_h/exp2/space_preview")
# Elements that must hold content once a tab is drawn
FILLED = {"pile": ["overview-plot", "class-bars", "noise-plot", "patterns-plot", "topics-plot", "concept-table"],
          "rollouts": ["named-forest", "named-cells", "named-means", "named-low", "named-docs", "named-split-docs", "named-split-missing", "named-scores", "named-pairs",
                       "noise-classes", "noise-lists", "noise-table", "named-selection", "lists-plot", "lists-table", "rollout-plot", "post-plot", "diag-figures", "diag-shape", "diag-moved", "diag-delta"]}


def show(path):
    return subprocess.run(["git", "show", f"{BASE_COMMIT}:space/{path}"], cwd=SPACE.parent, capture_output=True, check=True).stdout


def static_checks():
    bad = []
    new_html, js = (SPACE / "index.html").read_text(), (SPACE / "app.js").read_text()
    ids = set(re.findall(r'id="([^"]+)"', new_html))
    lost = set(re.findall(r'id="([^"]+)"', show("index.html").decode())) - ids - OLD_TABS
    if lost:
        bad.append(f"element ids lost: {sorted(lost)}")
    absent = set(re.findall(r'getElementById\("([^"]+)"\)', js)) - ids
    if absent:
        print("ids the script looks up that the page does not hold (may be made by the script):", sorted(absent), flush=True)
        if absent & set(re.findall(r'"(named[-\w]*|noise-[-\w]*|lists-[-\w]*|pairs-[-\w]*)"', js)):
            bad.append(f"names section ids absent from the page: {sorted(absent)}")
    for hash_ in re.findall(r'href="#([^"]+)"', new_html + js):
        if "$" not in hash_ and f"tab-{hash_}" not in ids and f"sec-{hash_}" not in ids:
            bad.append(f"link #{hash_} leads nowhere")
    plots = set(re.findall(r'Plotly\.(?:newPlot|react)\("([^"]+)"', js)) - ids
    if plots:
        bad.append(f"plots without a div: {sorted(plots)}")
    if "Temp visualizations" in new_html:
        bad.append("the old tab name is still on the page")
    return bad


def browser_checks():
    from playwright.sync_api import sync_playwright
    SHOTS.mkdir(parents=True, exist_ok=True)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(SPACE))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url, bad = f"http://127.0.0.1:{server.server_port}/index.html", []
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"])
        visits = [("pile", "pile", "pile"), ("rollouts", "rollouts", "rollouts"), ("old_overview", "overview", "pile"), ("old_noise", "noise", "pile"), ("old_patterns", "patterns", "pile"),
                  ("old_concepts", "concepts", "pile"), ("old_temp", "temp", "rollouts"), ("named_gap", "named-gap", "rollouts"), ("named_lists", "named-lists", "rollouts")]
        for name, hash_, tab in visits:
            page = browser.new_page(viewport={"width": 1280, "height": 1000})
            errors = []
            page.on("console", lambda m, e=errors: e.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda x, e=errors: e.append(str(x)))
            page.goto(f"{url}#{hash_}")
            page.wait_for_timeout(25000 if tab == "rollouts" else 15000)
            active = page.evaluate("document.querySelector('.tab.active')?.id")
            if active != f"tab-{tab}":
                bad.append(f"#{hash_}: active tab {active}")
            if name in FILLED:
                for el in FILLED[name]:
                    size = page.evaluate(f"(document.getElementById('{el}')?.innerHTML || '').length")
                    if size < 50:
                        bad.append(f"#{hash_}: {el} is empty ({size})")
            print(name, "active", active, "scrollY", page.evaluate("window.scrollY"), "errors", errors[:4], flush=True)
            bad += [f"#{hash_}: {e[:200]}" for e in errors if "favicon" not in e]
            page.screenshot(path=str(SHOTS / f"{name}.png"))
            if name == "pile":
                page.locator("#sec-concepts").screenshot(path=str(SHOTS / "part_sec-concepts.png"))
            if name == "rollouts":
                for el in ("named-forest", "named-cells", "named-docs", "sec-named-noise", "named-selection"):
                    page.locator(f"#{el}").screenshot(path=str(SHOTS / f"part_{el}.png"))
                page.select_option("#lists-model", "stage1")
                page.select_option("#pairs-group", "base")
                page.wait_for_timeout(1500)
                print("after filters:", page.evaluate("document.getElementById('lists-count').textContent"), "|", page.evaluate("document.getElementById('pairs-count').textContent"), flush=True)
                page.locator("#sec-named-lists").screenshot(path=str(SHOTS / "part_sec-named-lists.png"))
            page.close()
        browser.close()
    server.shutdown()
    return bad


def git_blob(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def snapshot(api):
    info = api.space_info(REPO, files_metadata=True)
    return info.sha, {s.rfilename: (s.lfs.sha256 if s.lfs else s.blob_id) for s in info.siblings}


def upload():
    from huggingface_hub import HfApi, hf_hub_download
    out = RESULTS / "full_post_space_named_nokey_check.json"
    report = {"repo": REPO, "base_commit": BASE_COMMIT, "uploaded": CODE + NEW}

    def stop(reason):
        report["result"] = "stopped: " + reason
        out.write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=1))
        sys.exit(1)

    bad = static_checks()
    if bad:
        stop(f"static checks: {bad}")
    missing = [f for f in NEW if not (SPACE / f).exists()]
    if missing:
        stop(f"run s23_space_named.py first; missing {missing}")
    api = HfApi(token=TOKEN_FILE.read_text().strip())
    sha_before, before = snapshot(api)
    report["before"] = {"commit": sha_before, "files": len(before)}
    edited = [f for f in CODE if before.get(f) != git_blob(show(f))]
    if edited:
        stop(f"remote {edited} differ from their {BASE_COMMIT} versions")
    clash = [f for f in NEW if f in before]
    if clash:
        stop(f"new paths already exist on the remote: {clash}")

    def attrs(rev):
        path = hf_hub_download(REPO, ".gitattributes", repo_type="space", revision=rev, token=api.token, cache_dir="/orcd/pool/005/angela_h/exp2/hf_space_check")
        return Path(path).read_text().splitlines()

    attrs_before = attrs(sha_before)
    commit = api.upload_folder(folder_path=str(SPACE), repo_id=REPO, repo_type="space", allow_patterns=CODE + NEW,
                               commit_message="Remove the key results box from the rollouts tab (G78)")
    sha_after, after = snapshot(api)
    report["after"] = {"commit": sha_after, "files": len(after), "upload_commit": str(commit)}
    changed = sorted(f for f in before if f in after and before[f] != after[f])
    report.update(changed_existing=changed, removed=sorted(f for f in before if f not in after), added=sorted(f for f in after if f not in before))
    bad = [f"changed: {f}" for f in changed if f not in CODE + [".gitattributes"]] + [f"removed: {f}" for f in report["removed"]]
    attrs_after = attrs(sha_after)
    report["gitattributes_added_lines"] = attrs_after[len(attrs_before):]
    if attrs_after[:len(attrs_before)] != attrs_before:
        bad.append(".gitattributes: existing lines changed")
    bad += [f".gitattributes: {line!r} names no new path" for line in attrs_after[len(attrs_before):] if line.split(" ")[0] not in NEW]
    for f in CODE + NEW:
        data = (SPACE / f).read_bytes()
        if after.get(f) not in {git_blob(data), hashlib.sha256(data).hexdigest()}:
            bad.append(f"remote {f} differs from the local file")
    if sorted(report["added"]) != sorted(NEW):
        bad.append(f"added paths {report['added']}")
    report["result"] = "ok" if not bad else f"failed: {bad}"
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=1))
    sys.exit(1 if bad else 0)


def check():
    bad = static_checks()
    print("static:", bad or "ok", flush=True)
    bad += browser_checks()
    print("failures:", bad or "none")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["check", "upload"])
    {"check": check, "upload": upload}[parser.parse_args().stage]()

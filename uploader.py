#!/usr/bin/env python3
"""
Automated GitHub File Uploader (Single-Repo & Multi-Repo Wise)
============================================================
Automates committing and uploading files to GitHub one-by-one to maintain
a consistent commit streak / activity on GitHub.

Key features:
- Repo-Wise Support: Upload to a single repository OR route across multiple repositories!
- Automatic folder-based routing: Drop files in `queue/<repo_name>/` to automatically target that repo.
- Target any local git repository on your machine using `--repo-dir`.
- Uploads 1 file per trigger/run (or N files with individual commits).
- Moves files safely from `queue/` to target directories.
- Backdating / Spread mode: Spreads commits across past days (1 commit/day).
- Daily scheduler (in-process daemon or Windows Task Scheduler integration).
- Complete history and status logging.
"""

import os
import sys
import json
import time
import shutil
import logging
import argparse
import subprocess
from pathlib import Path
from datetime import datetime, timedelta

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
HISTORY_PATH = BASE_DIR / "upload_history.json"
LOGS_DIR = BASE_DIR / "logs"

# Ensure logs directory exists
LOGS_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOGS_DIR / "uploader.log"

# Setup logging: both file and console
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("GitUploader")

DEFAULT_CONFIG = {
    "queue_dir": "queue",
    "target_dir": "uploads",
    "remote_name": "origin",
    "branch": "main",
    "git_user_name": "konark-17",
    "git_user_email": "kona300107@gmail.com",
    "commit_message_template": "Add {filename} - Daily commit [{date}]",
    "auto_push": True,
    "schedule_time": "10:00",
    "order": "alphabetical",  # "alphabetical", "oldest", "newest"
    "repos": {}
}


def load_config() -> dict:
    """Load config.json or create default if not present."""
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            merged = DEFAULT_CONFIG.copy()
            merged.update(data)
            return merged
    except Exception as e:
        logger.warning(f"Error reading config.json ({e}). Using default configuration.")
        return DEFAULT_CONFIG.copy()


def save_config(config: dict) -> None:
    """Save config to config.json."""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def load_history() -> list:
    """Load upload history from JSON."""
    if not HISTORY_PATH.exists():
        return []
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def record_history(entry: dict) -> None:
    """Append a completed upload to history."""
    history = load_history()
    history.append(entry)
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)


def run_git_cmd(args: list, cwd: Path = None, env: dict = None) -> subprocess.CompletedProcess:
    """Run a git command in the target repository directory."""
    target_cwd = cwd if cwd is not None else BASE_DIR
    cmd_env = os.environ.copy()
    if env:
        cmd_env.update(env)
    return subprocess.run(
        ["git"] + args,
        cwd=str(target_cwd),
        env=cmd_env,
        capture_output=True,
        text=True,
        check=False,
    )


def resolve_repo_context(
    config: dict,
    repo_name: str = None,
    rel_file: Path = None,
    override_repo_dir: str = None,
) -> tuple[dict, str, Path]:
    """
    Resolve which repository configuration to use.
    Supports single-repo, multi-repo profiles, and direct local repo folders.
    Returns: (merged_config, repo_key, repo_root_path)
    """
    repos = config.get("repos", {})

    # If direct repo dir is overridden via CLI
    if override_repo_dir:
        repo_root = Path(override_repo_dir).resolve()
        merged = config.copy()
        merged["repo_path"] = str(repo_root)
        merged["active_repo_key"] = repo_root.name
        return merged, repo_root.name, repo_root

    selected_key = repo_name

    # If repo_name not given, check if file is nested inside queue/<repo_name>/...
    if not selected_key and rel_file and repos:
        first_segment = rel_file.parts[0] if len(rel_file.parts) > 1 else None
        if first_segment and first_segment in repos:
            selected_key = first_segment

    if not selected_key or selected_key not in repos:
        return config.copy(), None, None

    repo_conf = repos[selected_key].copy()
    merged = config.copy()
    merged.update(repo_conf)
    merged["active_repo_key"] = selected_key

    # Resolve local git root directory
    if merged.get("repo_path"):
        repo_root = Path(merged["repo_path"]).resolve()
    elif selected_key in ("TEST", "leetcode") or not merged.get("remote_url"):
        repo_root = BASE_DIR
    else:
        # Isolated local git repository for distinct GitHub remotes (prevents overwriting BASE_DIR remote)
        repo_root = (BASE_DIR / "repos" / selected_key).resolve()

    # Fallback to local git remote URL if not specified in config
    if not merged.get("remote_url"):
        remote_name = merged.get("remote_name", "origin")
        res_r = run_git_cmd(["remote", "get-url", remote_name], cwd=repo_root)
        if res_r.returncode == 0 and res_r.stdout.strip():
            merged["remote_url"] = res_r.stdout.strip()

    return merged, selected_key, repo_root


def ensure_git_setup(config: dict, repo_root: Path = BASE_DIR) -> None:
    """Ensure repository has git initialized, user identity, and remote set."""
    if not repo_root.exists():
        repo_root.mkdir(parents=True, exist_ok=True)

    # Check if inside git repo
    res = run_git_cmd(["rev-parse", "--is-inside-work-tree"], cwd=repo_root)
    if res.returncode != 0:
        logger.info(f"Initializing new git repository in: {repo_root}")
        run_git_cmd(["init", "-b", config.get("branch", "main")], cwd=repo_root)

    # Configure local git user identity so GitHub links commits properly
    if config.get("git_user_name"):
        run_git_cmd(["config", "user.name", config["git_user_name"]], cwd=repo_root)
    if config.get("git_user_email"):
        run_git_cmd(["config", "user.email", config["git_user_email"]], cwd=repo_root)

    # Remote URL check / update
    remote_url = config.get("remote_url", "").strip()
    remote_name = config.get("remote_name", "origin")
    if remote_url:
        res = run_git_cmd(["remote", "get-url", remote_name], cwd=repo_root)
        if res.returncode == 0:
            current_remote = res.stdout.strip()
            if current_remote != remote_url:
                logger.info(f"[{repo_root.name}] Updating remote '{remote_name}' to: {remote_url}")
                run_git_cmd(["remote", "set-url", remote_name, remote_url], cwd=repo_root)
        else:
            logger.info(f"[{repo_root.name}] Adding remote '{remote_name}': {remote_url}")
            run_git_cmd(["remote", "add", remote_name, remote_url], cwd=repo_root)


def get_queued_files(config: dict, repo_filter: str = None) -> list[Path]:
    """Find all valid files waiting in queue directory (optionally filtered by repo)."""
    queue_dir = BASE_DIR / config.get("queue_dir", "queue")
    if not queue_dir.exists():
        queue_dir.mkdir(parents=True, exist_ok=True)
        return []

    ignore_names = {".gitkeep", ".DS_Store", "desktop.ini", "Thumbs.db"}
    candidates = []

    for root, dirs, files in os.walk(queue_dir):
        # Do not enter .git directories
        dirs[:] = [d for d in dirs if d != ".git"]
        if ".git" in Path(root).parts:
            continue
        for file in files:
            if file in ignore_names or file.startswith("."):
                continue
            full_path = Path(root) / file
            rel_path = full_path.relative_to(queue_dir)

            # If repo_filter specified, check match
            if repo_filter:
                first_part = rel_path.parts[0] if len(rel_path.parts) > 1 else None
                if first_part != repo_filter:
                    continue

            candidates.append((full_path, rel_path))

    order = config.get("order", "alphabetical")
    if order == "oldest":
        candidates.sort(key=lambda x: x[0].stat().st_mtime)
    elif order == "newest":
        candidates.sort(key=lambda x: x[0].stat().st_mtime, reverse=True)
    else:  # alphabetical
        candidates.sort(key=lambda x: str(x[1]).lower())

    return [rel for _, rel in candidates]


def get_unique_target_path(target_base: Path, rel_path: Path) -> Path:
    """Generate target file path, resolving collision if filename already exists."""
    dest = target_base / rel_path
    if not dest.exists():
        return dest

    stem = dest.stem
    suffix = dest.suffix
    parent = dest.parent
    counter = 1
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def upload_single_file(
    config: dict,
    repo_name: str = None,
    override_repo_dir: str = None,
    custom_date: datetime = None,
    dry_run: bool = False,
) -> dict:
    """
    Pick the next file from queue, move it to target repo, commit, and push.
    Returns status dict.
    """
    queue_dir = BASE_DIR / config.get("queue_dir", "queue")

    queued_files = get_queued_files(config, repo_filter=repo_name)
    if not queued_files:
        filter_msg = f" for repository '{repo_name}'" if repo_name else ""
        logger.warning(
            f"No files found in '{queue_dir}'{filter_msg}. Drop files into the queue to upload!"
        )
        return {
            "success": False,
            "message": "Queue is empty",
            "files_remaining": 0,
        }

    rel_file = queued_files[0]
    source_file = queue_dir / rel_file

    # Resolve repo context (merged config, repo key, and repo root)
    repo_config, active_key, repo_root = resolve_repo_context(
        config,
        repo_name=repo_name,
        rel_file=rel_file,
        override_repo_dir=override_repo_dir,
    )
    if not active_key or not repo_root:
        avail = ", ".join(config.get("repos", {}).keys()) or "None configured"
        err_msg = (
            f"Repository selection is compulsory! No repository selected for '{rel_file}'. "
            f"Please specify --repo <name> or place files inside 'queue/<repo_name>/'. "
            f"Configured repositories: {avail}"
        )
        logger.error(err_msg)
        return {"success": False, "message": err_msg}

    ensure_git_setup(repo_config, repo_root=repo_root)

    # If the file was in queue/<active_key>/file.ext, strip the repo folder prefix for the target destination
    if len(rel_file.parts) > 1 and rel_file.parts[0] == active_key and active_key in config.get("repos", {}):
        target_subpath = Path(*rel_file.parts[1:])
    else:
        target_subpath = rel_file

    target_dir_conf = repo_config.get("target_dir", "uploads")
    if repo_root != BASE_DIR and (not target_dir_conf or target_dir_conf.startswith("uploads")):
        target_base = repo_root
    else:
        target_base = repo_root / target_dir_conf
    target_base.mkdir(parents=True, exist_ok=True)

    dest_file = get_unique_target_path(target_base, target_subpath)
    dest_rel_repo = dest_file.relative_to(repo_root).as_posix()

    now = datetime.now()
    commit_dt = custom_date if custom_date else now
    date_str = commit_dt.strftime("%Y-%m-%d")
    date_iso = commit_dt.strftime("%Y-%m-%d %H:%M:%S")

    # Format commit message
    template = repo_config.get(
        "commit_message_template", "Add {filename} - Daily commit [{date}]"
    )
    commit_msg = template.format(
        filename=source_file.name,
        date=date_str,
        datetime=date_iso,
        repo=active_key,
    )

    remaining_after = len(queued_files) - 1

    if dry_run:
        logger.info(f"[DRY-RUN] [Repo: {active_key}] Would move: {source_file} -> {dest_file}")
        logger.info(f"[DRY-RUN] Commit date: {date_iso}")
        logger.info(f"[DRY-RUN] Commit message: '{commit_msg}'")
        logger.info(f"[DRY-RUN] Files remaining: {remaining_after}")
        return {
            "success": True,
            "dry_run": True,
            "file": str(rel_file),
            "repo": active_key,
            "files_remaining": remaining_after,
        }

    # 1. Move file
    dest_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source_file), str(dest_file))
    logger.info(f"[{active_key}] Moved file: {rel_file} -> {dest_rel_repo}")

    # 2. Git stage (stage target file and source location in case source was previously tracked)
    try:
        source_rel_repo = source_file.relative_to(repo_root).as_posix()
        res_add = run_git_cmd(["add", "-A", "--", dest_rel_repo, source_rel_repo], cwd=repo_root)
    except ValueError:
        # source_file was outside repo_root (e.g. queue was in central folder)
        res_add = run_git_cmd(["add", dest_rel_repo], cwd=repo_root)

    if res_add.returncode != 0:
        res_add = run_git_cmd(["add", dest_rel_repo], cwd=repo_root)

    if res_add.returncode != 0:
        error_msg = f"git add failed: {res_add.stderr.strip()}"
        logger.error(error_msg)
        return {"success": False, "message": error_msg}

    # 3. Git commit with custom date support (sets author and committer dates)
    git_env = {
        "GIT_AUTHOR_DATE": date_iso,
        "GIT_COMMITTER_DATE": date_iso,
    }
    res_commit = run_git_cmd(["commit", "-m", commit_msg], cwd=repo_root, env=git_env)
    if res_commit.returncode != 0:
        error_msg = f"git commit failed: {res_commit.stderr.strip()}"
        logger.error(error_msg)
        return {"success": False, "message": error_msg}

    # Get commit hash
    res_rev = run_git_cmd(["rev-parse", "HEAD"], cwd=repo_root)
    commit_hash = res_rev.stdout.strip()[:7] if res_rev.returncode == 0 else "unknown"

    logger.info(f"[{active_key}] Committed [{commit_hash}] '{commit_msg}' for date: {date_iso}")

    # 4. Git push (if configured)
    pushed = False
    remote_url = repo_config.get("remote_url", "").strip()
    auto_push = repo_config.get("auto_push", True)
    remote_name = repo_config.get("remote_name", "origin")
    branch = repo_config.get("branch", "main")

    if auto_push:
        if not remote_url:
            logger.warning(
                f"[{active_key}] Remote URL is not set. Commit saved locally in {repo_root.name}. "
                "Set 'remote_url' to push to GitHub automatically."
            )
        else:
            logger.info(f"[{active_key}] Pushing to {remote_name}/{branch}...")
            res_push = run_git_cmd(["push", "-u", remote_name, branch], cwd=repo_root)
            if res_push.returncode == 0:
                pushed = True
                logger.info(f"[{active_key}] Successfully pushed commit to GitHub!")
            else:
                logger.warning(
                    f"[{active_key}] git push failed ({res_push.stderr.strip()}). "
                    "The commit remains safe locally. Check internet connection or credentials."
                )

    # 5. Record to history
    entry = {
        "filename": source_file.name,
        "repo": active_key,
        "source_path": str(rel_file),
        "target_path": str(dest_rel_repo),
        "commit_hash": commit_hash,
        "commit_message": commit_msg,
        "commit_date": date_iso,
        "pushed": pushed,
        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
    }
    record_history(entry)

    logger.info(
        f"[SUCCESS] [{active_key}] Uploaded '{source_file.name}'. {remaining_after} file(s) remaining in queue."
    )
    return {
        "success": True,
        "file": str(rel_file),
        "repo": active_key,
        "commit_hash": commit_hash,
        "commit_date": date_iso,
        "pushed": pushed,
        "files_remaining": remaining_after,
    }


def sync_all_github_repos(config: dict, username: str = None, token: str = None) -> dict:
    """
    Fetch all repositories from the user's GitHub account and register them into config.json.
    Also creates queue subfolders for each repository so files can be dropped immediately.
    """
    import urllib.request
    user = (username or config.get("git_user_name", "konark-17")).strip()
    headers = {"User-Agent": "GitFlow-Uploader/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token.strip()}"
        url = "https://api.github.com/user/repos?per_page=100&sort=updated"
    else:
        url = f"https://api.github.com/users/{user}/repos?per_page=100&sort=updated"

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            repos_data = json.loads(response.read().decode())
    except Exception as e:
        logger.error(f"Failed to fetch repos from GitHub for {user}: {e}")
        return {"success": False, "message": f"GitHub request failed: {e}"}

    repos = config.get("repos", {})
    queue_dir = BASE_DIR / config.get("queue_dir", "queue")
    queue_dir.mkdir(parents=True, exist_ok=True)

    added = []
    updated = []

    for r in repos_data:
        name = r.get("name")
        clone_url = r.get("clone_url")
        branch = r.get("default_branch", "main")
        target_dir = f"uploads/{name}"

        is_new = name not in repos
        repos[name] = {
            "remote_url": clone_url,
            "branch": branch,
            "target_dir": target_dir,
            "description": r.get("description") or "",
        }

        # Create queue subfolder for this repo
        (queue_dir / name).mkdir(parents=True, exist_ok=True)

        if is_new:
            added.append(name)
        else:
            updated.append(name)

    config["repos"] = repos
    save_config(config)

    logger.info(
        f"Synced {len(repos_data)} repositories from GitHub account '{user}' "
        f"({len(added)} new, {len(updated)} updated)."
    )

    return {
        "success": True,
        "username": user,
        "total_account_repos": len(repos_data),
        "added_count": len(added),
        "updated_count": len(updated),
        "added_repos": added,
        "all_repos": list(repos.keys()),
        "message": f"Successfully synced {len(repos_data)} repositories from GitHub account '{user}'!",
    }


def reconcile_history(repo_root: Path = BASE_DIR, branch: str = "main", remote_name: str = "origin") -> int:
    """
    Checks each commit in upload_history.json. If it is already merged into the remote branch,
    updates its status to pushed: True.
    """
    history = load_history()
    updated_count = 0
    upstream = f"{remote_name}/{branch}"
    for item in history:
        if not item.get("pushed"):
            h = item.get("commit_hash")
            if h and h != "unknown":
                res = run_git_cmd(["merge-base", "--is-ancestor", h, upstream], cwd=repo_root)
                if res.returncode == 0:
                    item["pushed"] = True
                    updated_count += 1
    if updated_count > 0:
        with open(HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
    return updated_count


def get_sync_status(config: dict, repo_name: str = None, repo_root: Path = None) -> dict:
    """
    Get detailed GitHub synchronization status:
    - Remote URL
    - Upstream branch
    - Unpushed (ahead) commits count
    - Unpulled (behind) commits count
    - Reachability / Auth status
    """
    if repo_root is None:
        repo_cfg, active_key, repo_root = resolve_repo_context(config, repo_name=repo_name)
    else:
        repo_cfg, active_key, _ = resolve_repo_context(config, repo_name=repo_name)

    remote_name = repo_cfg.get("remote_name", "origin")
    branch = repo_cfg.get("branch", "main")
    remote_url = repo_cfg.get("remote_url", "").strip()

    # If remote_url is empty in config, check if git remote has one
    if not remote_url:
        res = run_git_cmd(["remote", "get-url", remote_name], cwd=repo_root)
        if res.returncode == 0:
            remote_url = res.stdout.strip()

    if not remote_url:
        return {
            "configured": False,
            "connected": False,
            "remote_url": "",
            "branch": branch,
            "repo_name": active_key,
            "ahead": 0,
            "behind": 0,
            "status_text": "No GitHub remote repository connected",
            "badge_color": "slate",
        }

    # Test reachability with git ls-remote (fast check)
    ls_res = run_git_cmd(["ls-remote", "--exit-code", "-h", remote_url], cwd=repo_root)
    reachable = (ls_res.returncode == 0)

    # Check upstream tracking
    upstream_res = run_git_cmd(["rev-parse", "--abbrev-ref", "@{u}"], cwd=repo_root)
    has_upstream = (upstream_res.returncode == 0)

    ahead = 0
    behind = 0
    if has_upstream:
        c_ahead = run_git_cmd(["rev-list", "--count", "@{u}..HEAD"], cwd=repo_root)
        if c_ahead.returncode == 0:
            try:
                ahead = int(c_ahead.stdout.strip())
            except ValueError:
                ahead = 0
        c_behind = run_git_cmd(["rev-list", "--count", "HEAD..@{u}"], cwd=repo_root)
        if c_behind.returncode == 0:
            try:
                behind = int(c_behind.stdout.strip())
            except ValueError:
                behind = 0
    else:
        c_local = run_git_cmd(["rev-list", "--count", "HEAD"], cwd=repo_root)
        if c_local.returncode == 0:
            try:
                ahead = int(c_local.stdout.strip())
            except ValueError:
                ahead = 0

    if not reachable:
        status_text = "Remote unreachable (Check URL or internet connection)"
        badge_color = "red"
    elif ahead > 0 and behind > 0:
        status_text = f"Diverged ({ahead} unpushed, {behind} unpulled)"
        badge_color = "amber"
    elif ahead > 0:
        status_text = f"{ahead} commit(s) ready to push to GitHub"
        badge_color = "amber"
    elif behind > 0:
        status_text = f"{behind} commit(s) waiting to be pulled from GitHub"
        badge_color = "blue"
    else:
        status_text = "Fully in sync with GitHub"
        badge_color = "emerald"

    return {
        "configured": True,
        "connected": reachable,
        "remote_url": remote_url,
        "branch": branch,
        "repo_name": active_key,
        "has_upstream": has_upstream,
        "ahead": ahead,
        "behind": behind,
        "status_text": status_text,
        "badge_color": badge_color,
    }


def sync_repo(
    config: dict,
    repo_name: str = None,
    remote_url: str = None,
    branch: str = None,
    action: str = "sync",  # "sync" (both), "push", "pull"
) -> dict:
    """
    Sync local repository with remote GitHub repository.
    Handles:
    - Setting/updating remote URL
    - Pulling with rebase/autostash
    - Pushing with upstream tracking
    - Reconciling history
    """
    repo_cfg, active_key, repo_root = resolve_repo_context(config, repo_name=repo_name)

    if remote_url:
        repo_cfg["remote_url"] = remote_url.strip()
    if branch:
        repo_cfg["branch"] = branch.strip()

    # Save to config if URL was updated
    if remote_url or branch:
        if active_key in config.get("repos", {}):
            if remote_url:
                config["repos"][active_key]["remote_url"] = remote_url.strip()
            if branch:
                config["repos"][active_key]["branch"] = branch.strip()
        else:
            if remote_url:
                config["remote_url"] = remote_url.strip()
            if branch:
                config["branch"] = branch.strip()
        save_config(config)

    ensure_git_setup(repo_cfg, repo_root=repo_root)

    eff_remote_url = repo_cfg.get("remote_url", "").strip()
    remote_name = repo_cfg.get("remote_name", "origin")
    eff_branch = repo_cfg.get("branch", "main")

    if not eff_remote_url:
        return {
            "success": False,
            "message": "No remote URL configured. Please enter your GitHub repository URL.",
        }

    logger.info(f"[{active_key}] Starting GitHub sync for {eff_remote_url} (branch: {eff_branch})...")
    pulled_count = 0
    pushed_count = 0

    # 1. Fetch
    fetch_res = run_git_cmd(["fetch", remote_name], cwd=repo_root)
    if fetch_res.returncode != 0:
        logger.warning(f"git fetch notice: {fetch_res.stderr.strip() or fetch_res.stdout.strip()}")

    # 2. Pull if action is 'pull' or 'sync'
    if action in ("pull", "sync"):
        pull_res = run_git_cmd(
            ["pull", "--rebase", "--autostash", remote_name, eff_branch],
            cwd=repo_root,
        )
        if pull_res.returncode == 0:
            logger.info(f"[{active_key}] Pull completed successfully.")
        else:
            if "couldn't find remote ref" in pull_res.stderr.lower() or "does not exist" in pull_res.stderr.lower():
                logger.info(f"[{active_key}] Remote branch {eff_branch} will be created on push.")
            else:
                logger.warning(f"[{active_key}] Pull notice: {pull_res.stderr.strip() or pull_res.stdout.strip()}")

    # 3. Push if action is 'push' or 'sync'
    if action in ("push", "sync"):
        c_res = run_git_cmd(["rev-list", "--count", f"{remote_name}/{eff_branch}..HEAD"], cwd=repo_root)
        unpushed = int(c_res.stdout.strip()) if c_res.returncode == 0 else 0

        push_res = run_git_cmd(["push", "-u", remote_name, eff_branch], cwd=repo_root)
        if push_res.returncode == 0:
            pushed_count = max(unpushed, 1)
            logger.info(f"[{active_key}] Push completed successfully!")
        else:
            err = push_res.stderr.strip()
            if "rejected" in err and action == "push":
                logger.info("Push was rejected because remote has new changes. Pulling with rebase and retrying...")
                run_git_cmd(["pull", "--rebase", "--autostash", remote_name, eff_branch], cwd=repo_root)
                push_res2 = run_git_cmd(["push", "-u", remote_name, eff_branch], cwd=repo_root)
                if push_res2.returncode == 0:
                    pushed_count = max(unpushed, 1)
                else:
                    return {"success": False, "message": f"git push failed: {push_res2.stderr.strip()}"}
            else:
                return {"success": False, "message": f"git push failed: {err}"}

    # 4. Reconcile history
    reconciled = reconcile_history(repo_root=repo_root, branch=eff_branch, remote_name=remote_name)
    if reconciled > 0:
        logger.info(f"[{active_key}] Reconciled {reconciled} history records to (Pushed: True).")

    # 5. Get fresh sync status
    status_info = get_sync_status(config, repo_name=active_key, repo_root=repo_root)

    return {
        "success": True,
        "message": f"Successfully synchronized with GitHub ({eff_remote_url})!",
        "reconciled_history": reconciled,
        "status": status_info,
    }


def upload_batch(
    config: dict,
    repo_name: str = None,
    override_repo_dir: str = None,
    count: int = 1,
    spread_days: bool = False,
    days_back: int = None,
    dry_run: bool = False,
) -> None:
    """Upload multiple files, optionally spreading them across distinct days."""
    queued = get_queued_files(config, repo_filter=repo_name)
    total_in_queue = len(queued)
    if total_in_queue == 0:
        logger.warning("Queue is empty. Drop files into 'queue/' folder first.")
        return

    n = min(count, total_in_queue)
    logger.info(f"Starting batch upload for {n} file(s) (total matching in queue: {total_in_queue})...")

    now = datetime.now()
    if spread_days:
        total_days = days_back if days_back is not None else n
        dates = [
            now - timedelta(days=float(total_days) * (n - 1 - i) / max(1, n - 1))
            for i in range(n)
        ]
    else:
        dates = [None] * n

    success_count = 0
    for i in range(n):
        dt = dates[i]
        logger.info(f"--- Processing file {i + 1}/{n} ---")
        result = upload_single_file(
            config,
            repo_name=repo_name,
            override_repo_dir=override_repo_dir,
            custom_date=dt,
            dry_run=dry_run,
        )
        if result.get("success"):
            success_count += 1
        else:
            logger.error(f"Failed at item {i + 1}: {result.get('message')}")
            break

    logger.info(f"Batch completed: {success_count}/{n} file(s) uploaded successfully.")


def run_daemon_schedule(config: dict, target_time_str: str, repo_name: str = None) -> None:
    """
    Run continuous daily schedule loop in-process.
    Waits until HH:MM every day and triggers 1 upload.
    """
    logger.info(f"Starting GitHub Uploader Daemon. Scheduled daily at: {target_time_str}")
    logger.info("Press Ctrl+C to stop.")

    while True:
        now = datetime.now()
        try:
            target_hour, target_minute = map(int, target_time_str.split(":"))
        except ValueError:
            target_hour, target_minute = 10, 0

        target_today = now.replace(
            hour=target_hour, minute=target_minute, second=0, microsecond=0
        )
        if target_today <= now:
            target_run = target_today + timedelta(days=1)
        else:
            target_run = target_today

        wait_seconds = (target_run - now).total_seconds()
        hours_left = wait_seconds / 3600.0
        logger.info(f"Next upload scheduled at {target_run.strftime('%Y-%m-%d %H:%M:%S')} (in {hours_left:.1f} hours). Waiting...")

        try:
            time.sleep(wait_seconds)
            logger.info("Triggering scheduled daily upload...")
            upload_single_file(config, repo_name=repo_name)
            time.sleep(60)
        except KeyboardInterrupt:
            logger.info("Daemon stopped by user.")
            break


def show_status(config: dict) -> None:
    """Print status of the queue, repos, history, and git configuration."""
    queue_dir = BASE_DIR / config.get("queue_dir", "queue")
    queued_files = get_queued_files(config)
    history = load_history()
    repos = config.get("repos", {})

    print("\n" + "=" * 65)
    print("      AUTOMATED GITHUB UPLOADER - SYSTEM STATUS (REPO-WISE)")
    print("=" * 65)
    print(f"Project Directory : {BASE_DIR}")
    print(f"Queue Directory   : {queue_dir}")
    print(f"Git Author        : {config.get('git_user_name')} <{config.get('git_user_email')}>")
    print(f"Auto-Push to Git  : {config.get('auto_push')}")

    print("-" * 65)
    print("REPOSITORIES CONFIGURED:")
    if repos:
        for r_name, r_cfg in repos.items():
            url = r_cfg.get("remote_url") or "(Local commits only)"
            br = r_cfg.get("branch", "main")
            path = r_cfg.get("repo_path") or "(This project folder)"
            print(f"   * [{r_name}] -> {url} [Branch: {br}]")
            if r_cfg.get("repo_path"):
                print(f"     Path: {path}")
    else:
        print("   (No repositories configured. Add one using --sync-all-github or the web app!)")

    print("-" * 65)
    print(f"Files in Queue    : {len(queued_files)}")
    if queued_files:
        print("Queued items:")
        for idx, file in enumerate(queued_files[:8], 1):
            first_part = file.parts[0] if len(file.parts) > 1 else None
            tag = f"[{first_part}]" if (first_part and first_part in repos) else "[UNASSIGNED - Move into a repo folder!]"
            print(f"   {idx}. {tag} {file}")
        if len(queued_files) > 8:
            print(f"   ... and {len(queued_files) - 8} more")
    else:
        print("   (Queue is empty. Drop files into a repository folder under 'queue/' to upload!)")

    print("-" * 65)
    print(f"Total Committed   : {len(history)}")
    if history:
        print("Recent uploads:")
        for item in history[-5:]:
            date_info = item.get("commit_date") or item.get("timestamp")
            repo_tag = f"[{item.get('repo', 'unassigned')}]"
            print(f"   * {repo_tag} [{item.get('commit_hash')}] {item.get('filename')} on {date_info} (Pushed: {item.get('pushed')})")
    print("=" * 65 + "\n")


def interactive_setup() -> None:
    """CLI wizard to configure repos, author info, and preferences."""
    config = load_config()
    print("\n" + "=" * 65)
    print("       GITHUB UPLOADER CONFIGURATION WIZARD")
    print("=" * 65)

    print("\nSelect Setup Mode:")
    print("  1. Add / Update a Named Repository Profile")
    print("  2. Sync All Repositories From GitHub Account")
    print("  3. Set Git Author Identity (Name & Email)")
    choice = input("Enter choice (1-3) [1]: ").strip() or "1"

    if choice == "2":
        res = sync_all_github_repos(config)
        print(f"\n[SUCCESS] {res.get('message')}")

    elif choice == "3":
        name = input(f"Git author name [{config.get('git_user_name', 'konark-17')}]: ").strip()
        email = input(f"Git author email [{config.get('git_user_email', 'kona300107@gmail.com')}]: ").strip()
        if name:
            config["git_user_name"] = name
        if email:
            config["git_user_email"] = email
        save_config(config)
        print("\n[SUCCESS] Author details saved!")

    else:
        repos = config.get("repos", {})
        repo_name = input("Enter repository profile name (e.g. leetcode, RoutePulse): ").strip()
        if not repo_name:
            print("[CANCELLED] Profile name cannot be empty.")
            return

        current_entry = repos.get(repo_name, {})
        remote_url = input(f"GitHub Remote URL [{current_entry.get('remote_url', '')}]: ").strip()
        branch = input(f"Branch name [{current_entry.get('branch', 'main')}]: ").strip() or "main"
        repo_path = input(f"Local repo path (Leave empty to use this folder) [{current_entry.get('repo_path', '')}]: ").strip()
        target_dir = input(f"Target upload subfolder inside repo [{current_entry.get('target_dir', 'uploads/' + repo_name)}]: ").strip() or f"uploads/{repo_name}"

        entry = {
            "remote_url": remote_url if remote_url else current_entry.get("remote_url", ""),
            "branch": branch,
            "target_dir": target_dir,
        }
        if repo_path:
            entry["repo_path"] = repo_path

        repos[repo_name] = entry
        config["repos"] = repos
        save_config(config)
        print(f"\n[SUCCESS] Profile '{repo_name}' saved!")

    show_status(config)


def main():
    parser = argparse.ArgumentParser(
        description="Automated GitHub File Uploader (Single-Repo & Multi-Repo Wise)"
    )
    parser.add_argument(
        "--upload-one",
        action="store_true",
        help="Upload the next single file from the queue (default action)",
    )
    parser.add_argument(
        "--repo",
        type=str,
        default=None,
        help="Target a specific configured repository profile (e.g. --repo leetcode)",
    )
    parser.add_argument(
        "--repo-dir",
        type=str,
        default=None,
        help="Target a specific local git repository directory on disk",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=None,
        help="Upload N files one by one with individual commits",
    )
    parser.add_argument(
        "--spread",
        action="store_true",
        help="Spread uploads across multiple past days (1 commit per day) to build GitHub streak graph",
    )
    parser.add_argument(
        "--days-back",
        type=int,
        default=None,
        help="Number of days in the past to span the commits across (used with --spread)",
    )
    parser.add_argument(
        "--schedule",
        nargs="?",
        const="DEFAULT",
        help="Run continuously and upload 1 file daily at HH:MM (e.g. --schedule 10:00)",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show queue files, git setup, and upload history",
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Run interactive configuration wizard (add repos, remote URLs, author)",
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Synchronize with GitHub (pull remote updates, push all pending commits, and reconcile history)",
    )
    parser.add_argument(
        "--remote-url",
        type=str,
        default=None,
        help="GitHub remote URL to connect and sync with",
    )
    parser.add_argument(
        "--sync-all-github",
        nargs="?",
        const="DEFAULT",
        help="Fetch and register ALL repositories from your GitHub account (e.g. --sync-all-github konark-17)",
    )
    parser.add_argument(
        "--github-token",
        type=str,
        default=None,
        help="Optional GitHub Personal Access Token to include private repositories",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the upload process without moving files or making commits",
    )

    args = parser.parse_args()
    config = load_config()

    if args.setup:
        interactive_setup()
        return

    if args.sync_all_github:
        user = None if args.sync_all_github == "DEFAULT" else args.sync_all_github
        res = sync_all_github_repos(config, username=user, token=args.github_token)
        print("\n" + "=" * 65)
        print("      GITHUB ACCOUNT REPOSITORIES SYNC REPORT")
        print("=" * 65)
        print(f"Status   : {'[SUCCESS]' if res.get('success') else '[FAILED]'}")
        print(f"User     : {res.get('username')}")
        print(f"Total    : {res.get('total_account_repos', 0)} repositories found on GitHub")
        print(f"New      : {res.get('added_count', 0)} added to Target Options")
        print(f"Updated  : {res.get('updated_count', 0)} refreshed")
        if res.get('added_repos'):
            print(f"Added    : {', '.join(res['added_repos'])}")
        print("=" * 65 + "\n")
        return

    if args.sync:
        sync_res = sync_repo(
            config,
            repo_name=args.repo,
            remote_url=args.remote_url,
        )
        print("\n" + "=" * 65)
        print("      GITHUB REPOSITORY SYNCHRONIZATION REPORT")
        print("=" * 65)
        print(f"Status   : {'[SUCCESS]' if sync_res.get('success') else '[FAILED]'}")
        print(f"Message  : {sync_res.get('message')}")
        if sync_res.get('status'):
            st = sync_res['status']
            print(f"Remote   : {st.get('remote_url')}")
            print(f"Branch   : {st.get('branch')}")
            print(f"Details  : {st.get('status_text')}")
            print(f"History  : Reconciled {sync_res.get('reconciled_history', 0)} commit records to Pushed: True")
        print("=" * 65 + "\n")
        return

    if args.status:
        show_status(config)
        return

    if args.schedule:
        schedule_time = (
            config.get("schedule_time", "10:00")
            if args.schedule == "DEFAULT"
            else args.schedule
        )
        run_daemon_schedule(config, schedule_time, repo_name=args.repo)
        return

    if args.spread:
        queued = get_queued_files(config, repo_filter=args.repo)
        count = args.count if args.count else len(queued)
        upload_batch(
            config,
            repo_name=args.repo,
            override_repo_dir=args.repo_dir,
            count=count,
            spread_days=True,
            days_back=args.days_back,
            dry_run=args.dry_run,
        )
        return

    if args.count and args.count > 1:
        upload_batch(
            config,
            repo_name=args.repo,
            override_repo_dir=args.repo_dir,
            count=args.count,
            dry_run=args.dry_run,
        )
        return

    # Default action: upload 1 file right now
    result = upload_single_file(
        config,
        repo_name=args.repo,
        override_repo_dir=args.repo_dir,
        dry_run=args.dry_run,
    )
    if not result.get("success") and result.get("message") == "Queue is empty":
        show_status(config)


if __name__ == "__main__":
    main()

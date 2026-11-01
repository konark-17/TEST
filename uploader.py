#!/usr/bin/env python3
"""
Automated GitHub File Uploader
==============================
Automates committing and uploading files to GitHub one-by-one to maintain
a consistent commit streak / activity on GitHub.

Key features:
- Uploads 1 file per trigger/run (or N files with individual commits).
- Moves files safely from `queue/` to `uploads/`.
- Configurable commit messages, git author name, email, and branch.
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
    "remote_url": "",
    "git_user_name": "konark-17",
    "git_user_email": "kona300107@gmail.com",
    "commit_message_template": "Add {filename} - Daily commit [{date}]",
    "auto_push": True,
    "schedule_time": "10:00",
    "order": "alphabetical",  # "alphabetical", "oldest", "newest"
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
    """Run a git command in the repository."""
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


def ensure_git_setup(config: dict) -> None:
    """Ensure local repository has git initialized and identity set."""
    # Check if inside git repo
    res = run_git_cmd(["rev-parse", "--is-inside-work-tree"])
    if res.returncode != 0:
        logger.info("Initializing new git repository in workspace...")
        run_git_cmd(["init", "-b", config.get("branch", "main")])

    # Configure local git user identity so GitHub links commits properly
    if config.get("git_user_name"):
        run_git_cmd(["config", "user.name", config["git_user_name"]])
    if config.get("git_user_email"):
        run_git_cmd(["config", "user.email", config["git_user_email"]])

    # Remote URL check / update
    remote_url = config.get("remote_url", "").strip()
    remote_name = config.get("remote_name", "origin")
    if remote_url:
        res = run_git_cmd(["remote", "get-url", remote_name])
        if res.returncode == 0:
            current_remote = res.stdout.strip()
            if current_remote != remote_url:
                logger.info(f"Updating remote '{remote_name}' to: {remote_url}")
                run_git_cmd(["remote", "set-url", remote_name, remote_url])
        else:
            logger.info(f"Adding remote '{remote_name}': {remote_url}")
            run_git_cmd(["remote", "add", remote_name, remote_url])


def get_queued_files(config: dict) -> list[Path]:
    """Find all valid files waiting in queue directory."""
    queue_dir = BASE_DIR / config.get("queue_dir", "queue")
    if not queue_dir.exists():
        queue_dir.mkdir(parents=True, exist_ok=True)
        return []

    ignore_names = {".gitkeep", ".DS_Store", "desktop.ini", "Thumbs.db"}
    candidates = []

    for root, _, files in os.walk(queue_dir):
        for file in files:
            if file in ignore_names or file.startswith("."):
                continue
            full_path = Path(root) / file
            rel_path = full_path.relative_to(queue_dir)
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
    custom_date: datetime = None,
    dry_run: bool = False,
) -> dict:
    """
    Pick the next file from queue, move it to uploads, commit, and push.
    Returns status dict.
    """
    ensure_git_setup(config)

    queue_dir = BASE_DIR / config.get("queue_dir", "queue")
    target_dir = BASE_DIR / config.get("target_dir", "uploads")
    target_dir.mkdir(parents=True, exist_ok=True)

    queued_files = get_queued_files(config)
    if not queued_files:
        logger.warning(
            f"No files found in '{queue_dir}'. Drop some files into the queue folder to upload!"
        )
        return {
            "success": False,
            "message": "Queue is empty",
            "files_remaining": 0,
        }

    rel_file = queued_files[0]
    source_file = queue_dir / rel_file
    dest_file = get_unique_target_path(target_dir, rel_file)
    dest_rel_repo = dest_file.relative_to(BASE_DIR).as_posix()

    now = datetime.now()
    commit_dt = custom_date if custom_date else now
    date_str = commit_dt.strftime("%Y-%m-%d")
    date_iso = commit_dt.strftime("%Y-%m-%d %H:%M:%S")

    # Format commit message
    template = config.get(
        "commit_message_template", "Add {filename} - Daily commit [{date}]"
    )
    commit_msg = template.format(
        filename=source_file.name,
        date=date_str,
        datetime=date_iso,
    )

    remaining_after = len(queued_files) - 1

    if dry_run:
        logger.info(f"[DRY-RUN] Would move: {source_file} -> {dest_file}")
        logger.info(f"[DRY-RUN] Commit date: {date_iso}")
        logger.info(f"[DRY-RUN] Commit message: '{commit_msg}'")
        logger.info(f"[DRY-RUN] Files remaining: {remaining_after}")
        return {
            "success": True,
            "dry_run": True,
            "file": str(rel_file),
            "files_remaining": remaining_after,
        }

    # 1. Move file
    dest_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source_file), str(dest_file))
    logger.info(f"Moved file: {rel_file} -> {dest_rel_repo}")

    # 2. Git stage (stage target file and source location in case source was previously tracked)
    source_rel_repo = (BASE_DIR / config.get("queue_dir", "queue") / rel_file).relative_to(BASE_DIR).as_posix()
    res_add = run_git_cmd(["add", "-A", "--", dest_rel_repo, source_rel_repo])
    if res_add.returncode != 0:
        # Fallback to single add if pathspec had issues
        res_add = run_git_cmd(["add", dest_rel_repo])
    if res_add.returncode != 0:
        error_msg = f"git add failed: {res_add.stderr.strip()}"
        logger.error(error_msg)
        return {"success": False, "message": error_msg}

    # 3. Git commit with custom date support (sets author and committer dates)
    git_env = {
        "GIT_AUTHOR_DATE": date_iso,
        "GIT_COMMITTER_DATE": date_iso,
    }
    res_commit = run_git_cmd(["commit", "-m", commit_msg], env=git_env)
    if res_commit.returncode != 0:
        error_msg = f"git commit failed: {res_commit.stderr.strip()}"
        logger.error(error_msg)
        return {"success": False, "message": error_msg}

    # Get commit hash
    res_rev = run_git_cmd(["rev-parse", "HEAD"])
    commit_hash = res_rev.stdout.strip()[:7] if res_rev.returncode == 0 else "unknown"

    logger.info(f"Committed [{commit_hash}] '{commit_msg}' for date: {date_iso}")

    # 4. Git push (if configured)
    pushed = False
    remote_url = config.get("remote_url", "").strip()
    auto_push = config.get("auto_push", True)
    remote_name = config.get("remote_name", "origin")
    branch = config.get("branch", "main")

    if auto_push:
        if not remote_url:
            logger.warning(
                "Remote URL is not set in config.json. Commit is saved locally. "
                "Set 'remote_url' to push to GitHub automatically."
            )
        else:
            logger.info(f"Pushing to {remote_name}/{branch}...")
            res_push = run_git_cmd(["push", "-u", remote_name, branch])
            if res_push.returncode == 0:
                pushed = True
                logger.info("Successfully pushed commit to GitHub!")
            else:
                logger.warning(
                    f"git push failed ({res_push.stderr.strip()}). "
                    "The commit remains safe locally. Check internet connection or credentials."
                )

    # 5. Record to history
    entry = {
        "filename": source_file.name,
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
        f"[SUCCESS] Uploaded '{source_file.name}'. {remaining_after} file(s) remaining in queue."
    )
    return {
        "success": True,
        "file": str(rel_file),
        "commit_hash": commit_hash,
        "commit_date": date_iso,
        "pushed": pushed,
        "files_remaining": remaining_after,
    }


def upload_batch(
    config: dict,
    count: int = 1,
    spread_days: bool = False,
    days_back: int = None,
    dry_run: bool = False,
) -> None:
    """Upload multiple files, optionally spreading them across distinct days."""
    queued = get_queued_files(config)
    total_in_queue = len(queued)
    if total_in_queue == 0:
        logger.warning("Queue is empty. Drop files into 'queue/' folder first.")
        return

    n = min(count, total_in_queue)
    logger.info(f"Starting batch upload for {n} file(s) (total in queue: {total_in_queue})...")

    now = datetime.now()
    # If spreading across days, calculate dates
    if spread_days:
        total_days = days_back if days_back is not None else n
        # Spaced out dates: from (now - total_days) up to today
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
        result = upload_single_file(config, custom_date=dt, dry_run=dry_run)
        if result.get("success"):
            success_count += 1
        else:
            logger.error(f"Failed at item {i + 1}: {result.get('message')}")
            break

    logger.info(f"Batch completed: {success_count}/{n} file(s) uploaded successfully.")


def run_daemon_schedule(config: dict, target_time_str: str) -> None:
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
            # Scheduled time for today already passed; schedule for tomorrow
            target_run = target_today + timedelta(days=1)
        else:
            target_run = target_today

        wait_seconds = (target_run - now).total_seconds()
        hours_left = wait_seconds / 3600.0
        logger.info(f"Next upload scheduled at {target_run.strftime('%Y-%m-%d %H:%M:%S')} (in {hours_left:.1f} hours). Waiting...")

        try:
            time.sleep(wait_seconds)
            logger.info("Triggering scheduled daily upload...")
            upload_single_file(config)
            # Sleep 60 seconds to avoid double-triggering within the same minute
            time.sleep(60)
        except KeyboardInterrupt:
            logger.info("Daemon stopped by user.")
            break


def show_status(config: dict) -> None:
    """Print status of the queue, history, and git configuration."""
    queue_dir = BASE_DIR / config.get("queue_dir", "queue")
    target_dir = BASE_DIR / config.get("target_dir", "uploads")
    queued_files = get_queued_files(config)
    history = load_history()

    print("\n" + "=" * 60)
    print("      AUTOMATED GITHUB UPLOADER - SYSTEM STATUS")
    print("=" * 60)
    print(f"Project Directory : {BASE_DIR}")
    print(f"Queue Directory   : {queue_dir}")
    print(f"Uploads Directory : {target_dir}")
    print(f"Git Author        : {config.get('git_user_name')} <{config.get('git_user_email')}>")
    print(f"Remote URL        : {config.get('remote_url') or '(Not set - local commits only)'}")
    print(f"Target Branch     : {config.get('branch', 'main')}")
    print(f"Auto-Push to Git  : {config.get('auto_push')}")
    print("-" * 60)
    print(f"Files in Queue    : {len(queued_files)}")
    if queued_files:
        print("Next up:")
        for idx, file in enumerate(queued_files[:5], 1):
            print(f"   {idx}. {file}")
        if len(queued_files) > 5:
            print(f"   ... and {len(queued_files) - 5} more")
    else:
        print("   (Queue is empty. Drop files in 'queue/' to upload!)")
    print("-" * 60)
    print(f"Total Committed   : {len(history)}")
    if history:
        print("Recent uploads:")
        for item in history[-5:]:
            date_info = item.get("commit_date") or item.get("timestamp")
            print(f"   * [{item.get('commit_hash')}] {item.get('filename')} on {date_info} (Pushed: {item.get('pushed')})")
    print("=" * 60 + "\n")


def interactive_setup() -> None:
    """CLI wizard to configure remote, author info, and preferences."""
    config = load_config()
    print("\n" + "=" * 60)
    print("       GITHUB UPLOADER CONFIGURATION WIZARD")
    print("=" * 60)

    # Remote URL
    curr_url = config.get("remote_url", "")
    print(f"\nCurrent GitHub Repository Remote URL: {curr_url or 'None'}")
    new_url = input("Enter GitHub repository URL (e.g., https://github.com/konark-17/my-repo.git) [press Enter to keep]: ").strip()
    if new_url:
        config["remote_url"] = new_url

    # Git user name
    curr_name = config.get("git_user_name", "konark-17")
    new_name = input(f"Enter Git author name [{curr_name}]: ").strip()
    if new_name:
        config["git_user_name"] = new_name

    # Git user email
    curr_email = config.get("git_user_email", "kona300107@gmail.com")
    new_email = input(f"Enter Git author email [{curr_email}]: ").strip()
    if new_email:
        config["git_user_email"] = new_email

    # Schedule time
    curr_time = config.get("schedule_time", "10:00")
    new_time = input(f"Enter daily scheduled upload time (24h format HH:MM) [{curr_time}]: ").strip()
    if new_time:
        config["schedule_time"] = new_time

    # Save
    save_config(config)
    ensure_git_setup(config)
    print("\n[SUCCESS] Configuration saved to config.json!")
    show_status(config)


def main():
    parser = argparse.ArgumentParser(
        description="Automated GitHub File Uploader (One-by-one / Daily / Streak)"
    )
    parser.add_argument(
        "--upload-one",
        action="store_true",
        help="Upload the next single file from the queue (default action)",
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
        help="Run interactive configuration wizard",
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

    if args.status:
        show_status(config)
        return

    if args.schedule:
        schedule_time = (
            config.get("schedule_time", "10:00")
            if args.schedule == "DEFAULT"
            else args.schedule
        )
        run_daemon_schedule(config, schedule_time)
        return

    if args.spread:
        count = args.count if args.count else len(get_queued_files(config))
        upload_batch(
            config,
            count=count,
            spread_days=True,
            days_back=args.days_back,
            dry_run=args.dry_run,
        )
        return

    if args.count and args.count > 1:
        upload_batch(config, count=args.count, dry_run=args.dry_run)
        return

    # Default action: upload 1 file right now
    result = upload_single_file(config, dry_run=args.dry_run)
    if not result.get("success") and result.get("message") == "Queue is empty":
        show_status(config)


if __name__ == "__main__":
    main()

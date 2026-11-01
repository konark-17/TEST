#!/usr/bin/env python3
"""
Web Application Backend for Automated GitHub Uploader
=====================================================
Built with FastAPI, providing REST APIs and serving a modern,
responsive dashboard for queue management, multi-repo configuration,
streak builder, live logs, and Windows Task Scheduler automation.
"""

import os
import sys
import json
import shutil
import logging
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional, List

from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import uploader

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
STATIC_DIR = WEB_DIR / "static"
TEMPLATES_DIR = WEB_DIR / "templates"
LOGS_DIR = BASE_DIR / "logs"

app = FastAPI(title="Automated GitHub Uploader Dashboard", version="2.0")

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# Pydantic Request Models
class SingleUploadRequest(BaseModel):
    repo: Optional[str] = None
    override_repo_dir: Optional[str] = None
    dry_run: bool = False


class BatchUploadRequest(BaseModel):
    repo: Optional[str] = None
    override_repo_dir: Optional[str] = None
    count: int = 1
    spread_days: bool = False
    days_back: Optional[int] = None
    dry_run: bool = False


class ConfigUpdateRequest(BaseModel):
    git_user_name: Optional[str] = None
    git_user_email: Optional[str] = None
    remote_url: Optional[str] = None
    branch: Optional[str] = None
    auto_push: Optional[bool] = None
    schedule_time: Optional[str] = None
    order: Optional[str] = None


class RepoProfileRequest(BaseModel):
    name: str
    remote_url: Optional[str] = ""
    branch: Optional[str] = "main"
    repo_path: Optional[str] = ""
    target_dir: Optional[str] = "uploads"


class ScheduleInstallRequest(BaseModel):
    time: str = "10:00"


class SyncRequest(BaseModel):
    repo: Optional[str] = None
    remote_url: Optional[str] = None
    branch: Optional[str] = None
    action: str = "sync"  # "sync", "push", "pull"


def query_scheduler_status() -> dict:
    """Check status of GitHubDailyUploader scheduled task."""
    ps_file = BASE_DIR / "setup_scheduler.ps1"
    try:
        res = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ps_file),
                "-Action",
                "status",
            ],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        output = res.stdout.strip()
        is_installed = "Task 'GitHubDailyUploader' is NOT installed" not in output
        state = "Ready" if "State        : Ready" in output else ("Disabled" if "Disabled" in output else "Unknown")
        next_run = ""
        last_run = ""
        for line in output.splitlines():
            if line.startswith("Next Run"):
                next_run = line.split(":", 1)[1].strip()
            elif line.startswith("Last Run"):
                last_run = line.split(":", 1)[1].strip()
        return {
            "installed": is_installed,
            "state": state if is_installed else "Not Installed",
            "next_run": next_run,
            "last_run": last_run,
            "raw": output,
        }
    except Exception as e:
        return {"installed": False, "state": "Error checking", "error": str(e)}


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = TEMPLATES_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    return HTMLResponse(content=index_file.read_text(encoding="utf-8"))


@app.get("/api/status")
async def get_system_status():
    config = uploader.load_config()
    history = uploader.load_history()
    scheduler = query_scheduler_status()

    queue_dir = BASE_DIR / config.get("queue_dir", "queue")
    queue_files = []

    if queue_dir.exists():
        for full_path in queue_dir.rglob("*"):
            if full_path.is_file() and not full_path.name.startswith(".") and full_path.name != ".gitkeep":
                rel = full_path.relative_to(queue_dir)
                first_part = rel.parts[0] if len(rel.parts) > 1 else "default"
                stat = full_path.stat()
                queue_files.append({
                    "name": full_path.name,
                    "rel_path": str(rel).replace("\\", "/"),
                    "repo": first_part if first_part in config.get("repos", {}) else "default",
                    "size": stat.st_size,
                    "size_str": f"{stat.st_size / 1024:.1f} KB" if stat.st_size >= 1024 else f"{stat.st_size} B",
                    "mtime": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                })

    # Sort according to config
    order = config.get("order", "alphabetical")
    if order == "oldest":
        queue_files.sort(key=lambda x: x["mtime"])
    elif order == "newest":
        queue_files.sort(key=lambda x: x["mtime"], reverse=True)
    else:
        queue_files.sort(key=lambda x: x["rel_path"].lower())

    # Calculate repo stats
    repo_counts = {}
    for q in queue_files:
        r = q["repo"]
        repo_counts[r] = repo_counts.get(r, 0) + 1

    # Get GitHub Sync status
    sync_status = uploader.get_sync_status(config)

    return {
        "config": config,
        "queue": queue_files,
        "history": list(reversed(history)),  # newest first
        "scheduler": scheduler,
        "sync": sync_status,
        "stats": {
            "total_queued": len(queue_files),
            "total_committed": len(history),
            "repo_counts": repo_counts,
        },
    }


@app.get("/api/sync/status")
async def get_github_sync_status(repo: Optional[str] = None):
    config = uploader.load_config()
    status_info = uploader.get_sync_status(config, repo_name=repo)
    return status_info


@app.post("/api/sync")
async def sync_github(req: SyncRequest):
    config = uploader.load_config()
    res = uploader.sync_repo(
        config=config,
        repo_name=req.repo,
        remote_url=req.remote_url,
        branch=req.branch,
        action=req.action,
    )
    return res


@app.post("/api/upload-single")
async def trigger_single_upload(req: SingleUploadRequest):
    config = uploader.load_config()
    result = uploader.upload_single_file(
        config=config,
        repo_name=req.repo,
        override_repo_dir=req.override_repo_dir,
        dry_run=req.dry_run,
    )
    return result


@app.post("/api/upload-batch")
async def trigger_batch_upload(req: BatchUploadRequest):
    config = uploader.load_config()
    uploader.upload_batch(
        config=config,
        repo_name=req.repo,
        override_repo_dir=req.override_repo_dir,
        count=req.count,
        spread_days=req.spread_days,
        days_back=req.days_back,
        dry_run=req.dry_run,
    )
    return {"success": True, "message": "Batch processed successfully"}


@app.post("/api/queue/upload")
async def upload_files_to_queue(
    files: List[UploadFile] = File(...),
    repo: str = Form("default"),
):
    config = uploader.load_config()
    queue_dir = BASE_DIR / config.get("queue_dir", "queue")

    target_queue = queue_dir
    if repo and repo != "default":
        target_queue = queue_dir / repo

    target_queue.mkdir(parents=True, exist_ok=True)
    saved = []

    for file in files:
        file_path = target_queue / file.filename
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        saved.append(file.filename)

    return {"success": True, "saved_count": len(saved), "files": saved}


@app.delete("/api/queue/{file_path:path}")
async def delete_queue_file(file_path: str):
    config = uploader.load_config()
    queue_dir = BASE_DIR / config.get("queue_dir", "queue")
    target = queue_dir / file_path

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found in queue")

    try:
        target.unlink()
        return {"success": True, "message": f"Deleted {file_path}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/queue/preview/{file_path:path}")
async def preview_queue_file(file_path: str):
    config = uploader.load_config()
    queue_dir = BASE_DIR / config.get("queue_dir", "queue")
    target = queue_dir / file_path

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found in queue")

    try:
        # Read up to 20 KB
        with open(target, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(20480)
        return {
            "filename": target.name,
            "path": file_path,
            "content": content,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/config")
async def update_config(req: ConfigUpdateRequest):
    config = uploader.load_config()
    data = req.model_dump(exclude_unset=True)
    for k, v in data.items():
        if v is not None:
            config[k] = v
    uploader.save_config(config)
    uploader.ensure_git_setup(config)
    return {"success": True, "config": config}


@app.get("/api/github/user-repos")
async def get_github_user_repos(username: Optional[str] = None):
    """Fetch public repositories from GitHub for the user."""
    import urllib.request
    config = uploader.load_config()
    user = (username or config.get("git_user_name", "konark-17")).strip()
    url = f"https://api.github.com/users/{user}/repos?per_page=100&sort=updated"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "GitFlow-Uploader/1.0"})
        with urllib.request.urlopen(req, timeout=8) as response:
            repos_data = json.loads(response.read().decode())

        configured_repos = config.get("repos", {})
        result = []
        for r in repos_data:
            name = r.get("name")
            is_added = (name in configured_repos) or (config.get("remote_url", "").endswith(f"/{name}.git") or config.get("remote_url", "").endswith(f"/{name}"))
            result.append({
                "name": name,
                "full_name": r.get("full_name"),
                "clone_url": r.get("clone_url"),
                "html_url": r.get("html_url"),
                "description": r.get("description") or "",
                "default_branch": r.get("default_branch", "main"),
                "is_private": r.get("private", False),
                "is_added": is_added,
            })
        return {"success": True, "username": user, "repos": result}
    except Exception as e:
        logger.warning(f"Failed to fetch GitHub repos for {user}: {e}")
        return {"success": False, "username": user, "error": str(e), "repos": []}


@app.get("/api/repos/local-detected")
async def get_local_detected_repos():
    """Detect local git repositories in the parent workspace directory."""
    config = uploader.load_config()
    configured_repos = config.get("repos", {})
    parent_dir = BASE_DIR.parent
    detected = []
    if parent_dir.exists():
        for p in parent_dir.iterdir():
            if p.is_dir() and (p / ".git").exists() and p != BASE_DIR:
                res = uploader.run_git_cmd(["remote", "get-url", "origin"], cwd=p)
                remote_url = res.stdout.strip() if res.returncode == 0 else ""
                res_b = uploader.run_git_cmd(["branch", "--show-current"], cwd=p)
                branch = res_b.stdout.strip() or "main" if res_b.returncode == 0 else "main"
                is_added = any(r.get("repo_path") == str(p) or k == p.name for k, r in configured_repos.items())
                detected.append({
                    "name": p.name,
                    "path": str(p),
                    "remote_url": remote_url,
                    "branch": branch,
                    "is_added": is_added,
                })
    return {"success": True, "local_repos": detected}


@app.post("/api/repos")
async def add_or_update_repo(req: RepoProfileRequest):
    config = uploader.load_config()
    repos = config.get("repos", {})

    entry = {
        "remote_url": req.remote_url or "",
        "branch": req.branch or "main",
        "target_dir": req.target_dir or f"uploads/{req.name}",
    }
    if req.repo_path:
        entry["repo_path"] = req.repo_path

    repos[req.name] = entry
    config["repos"] = repos
    uploader.save_config(config)

    # Ensure queue directory for this repo exists
    queue_dir = BASE_DIR / config.get("queue_dir", "queue")
    (queue_dir / req.name).mkdir(parents=True, exist_ok=True)

    # Initialize / update git setup for this repo
    merged, _, root = uploader.resolve_repo_context(config, repo_name=req.name)
    uploader.ensure_git_setup(merged, repo_root=root)

    return {"success": True, "repo": req.name, "config": entry}


@app.delete("/api/repos/{repo_name}")
async def delete_repo_profile(repo_name: str):
    config = uploader.load_config()
    repos = config.get("repos", {})

    if repo_name not in repos:
        raise HTTPException(status_code=404, detail=f"Repo profile '{repo_name}' not found")

    del repos[repo_name]
    config["repos"] = repos
    uploader.save_config(config)
    return {"success": True, "message": f"Repo profile '{repo_name}' removed"}


@app.post("/api/repos/test-remote")
async def test_remote_connectivity(data: dict):
    url = data.get("remote_url", "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="remote_url is required")

    res = subprocess.run(
        ["git", "ls-remote", "--exit-code", "-h", url],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if res.returncode == 0:
        return {"success": True, "message": "Connection successful! Remote repository is reachable."}
    else:
        err = res.stderr.strip() or "Connection timed out or access denied."
        return {"success": False, "message": err}


@app.post("/api/scheduler/install")
async def install_scheduler(req: ScheduleInstallRequest):
    ps_file = BASE_DIR / "setup_scheduler.ps1"
    res = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ps_file),
            "-Action",
            "install",
            "-Time",
            req.time,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode == 0:
        return {"success": True, "message": f"Daily schedule registered for {req.time}!"}
    else:
        raise HTTPException(status_code=500, detail=res.stderr or res.stdout)


@app.post("/api/scheduler/remove")
async def remove_scheduler():
    ps_file = BASE_DIR / "setup_scheduler.ps1"
    res = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ps_file),
            "-Action",
            "remove",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return {"success": True, "message": "Scheduled task removed."}


@app.post("/api/scheduler/run-now")
async def run_scheduler_now():
    ps_file = BASE_DIR / "setup_scheduler.ps1"
    res = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ps_file),
            "-Action",
            "run",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return {"success": True, "message": "Scheduled task triggered."}


@app.get("/api/logs")
async def get_logs(lines: int = 100):
    log_file = LOGS_DIR / "uploader.log"
    if not log_file.exists():
        return {"logs": ["No logs generated yet."]}

    try:
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
            return {"logs": [line.rstrip() for line in all_lines[-lines:]]}
    except Exception as e:
        return {"logs": [f"Error reading logs: {e}"]}


if __name__ == "__main__":
    import uvicorn
    print("\n" + "=" * 65)
    print("  🚀 Starting Automated GitHub Uploader Web Application")
    print("  🌐 Dashboard URL: http://localhost:8000")
    print("=" * 65 + "\n")
    uvicorn.run("web_app:app", host="127.0.0.1", port=8000, reload=True)


# Automated GitHub File Uploader 🚀

An automated system to upload files to GitHub one by one to steadily increase your commit activity and maintain a daily GitHub contribution streak.

---

## 🌟 How It Works

1. **Queue Files**: Place any files (code solutions, notes, projects, markdown, etc.) inside the `queue/` folder.
2. **Trigger Upload**:
   - **On Demand**: Double-click `run_once.bat` or run `python uploader.py` to upload the next single file immediately.
   - **Automated Daily**: Use `setup_scheduler.bat` to have Windows automatically upload 1 file every day at your preferred time (e.g. 10:00 AM) in the background.
   - **Streak Builder**: Use `--spread` to commit a batch of files backdated across the last N days (1 commit per day) to light up your GitHub contribution graph.
3. **Commit & Push**:
   - The file is cleanly moved from `queue/` to `uploads/`.
   - Staged and committed with a custom date-stamped message.
   - Automatically pushed to your GitHub repository.
   - Progress is logged in `upload_history.json`.

---

## 🛠️ Quick Start

### 1. Configure GitHub Repo & Identity
Open [config.json](file:///c:/Users/KONARK/OneDrive/Desktop/project/Automated%20Github%20uploader/config.json):
```json
{
  "queue_dir": "queue",
  "target_dir": "uploads",
  "remote_name": "origin",
  "branch": "main",
  "remote_url": "https://github.com/konark-17/<your-repo-name>.git",
  "git_user_name": "konark-17",
  "git_user_email": "kona300107@gmail.com",
  "commit_message_template": "Add {filename} - Daily commit [{date}]",
  "auto_push": true,
  "schedule_time": "10:00",
  "order": "alphabetical"
}
```
> **Tip:** You can also run the interactive wizard:
> ```powershell
> python uploader.py --setup
> ```

### 2. Put Files in Queue
Drop any files you want uploaded into the `queue/` directory.

### 3. Trigger 1 Upload
Double-click `run_once.bat` or run:
```powershell
python uploader.py
```
This commits the next file and pushes it to your GitHub repository!

---

## ⏰ Automating Daily Uploads (Windows Task Scheduler)

To have Windows upload one file every day in the background without needing to keep a terminal open:

1. Double-click **`setup_scheduler.bat`** (or run `powershell -ExecutionPolicy Bypass -File setup_scheduler.ps1 -Action menu`).
2. Choose:
   - `1`: Install Daily Schedule (Runs daily at 10:00 AM)
   - `2`: Install with Custom Daily Time (e.g. `09:30` or `19:00`)
   - `3`: Check Scheduled Task Status
   - `4`: Test Run Task Now
   - `5`: Remove Scheduled Task

The scheduled task runs completely headless in the background and writes activity logs to `logs/uploader.log`.

---

## 🔥 Pro Feature: Commit Streak Builder (`--spread`)

If you have 10, 20, or 30 files in `queue/` and want them to appear as **1 commit per day** over the past 30 days on your GitHub contribution graph:

```powershell
# Spread all queued files across the past 30 days (1 commit each day)
python uploader.py --spread --days-back 30
```

This uses Git's `GIT_AUTHOR_DATE` and `GIT_COMMITTER_DATE` to legitimately backdate each individual commit on consecutive days, then pushes them to GitHub.

---

## 🔥 Multi-Repo & Repo-Wise Support

You can configure the uploader to target **a single repository**, **multiple named repositories**, or **any local git folder**:

### Method 1: Subfolder Auto-Routing (Recommended)
Place files in `queue/` grouped by repository name:
```
queue/
├── leetcode/
│   ├── problem_01.py
│   └── problem_02.py
└── networking/
    ├── packet_parser.go
    └── tcp_client.c
```
In `config.json`:
```json
{
  "repos": {
    "leetcode": {
      "remote_url": "https://github.com/konark-17/leetcode-solutions.git",
      "target_dir": "uploads/leetcode"
    },
    "networking": {
      "remote_url": "https://github.com/konark-17/networking-projects.git",
      "target_dir": "uploads/networking"
    }
  }
}
```
The uploader automatically detects the folder name (`leetcode`, `networking`) and commits to the corresponding repository!

### Method 2: Target a Specific Repo via CLI
```powershell
python uploader.py --repo leetcode
```

### Method 3: Target Any Local Git Repository on Your Disk
```powershell
python uploader.py --repo-dir "c:\Users\KONARK\OneDrive\Desktop\project\Low Latency"
```

---

## 💻 CLI Commands & Options

| Command | Description |
|---|---|
| `python uploader.py` | Upload next 1 file from queue right now |
| `python uploader.py --repo <name>` | Upload next file for a specific configured repository profile |
| `python uploader.py --repo-dir <path>` | Target any local git repository on your machine |
| `python uploader.py --dry-run` | Preview what file would be uploaded without changing anything |
| `python uploader.py --status` | View queue breakdown per repo, total committed, and git settings |
| `python uploader.py --count 3` | Upload 3 files one by one with 3 separate commits |
| `python uploader.py --spread --days-back 14` | Commit queued files backdated across the past 14 days |
| `python uploader.py --schedule 10:00` | Run continuously in terminal, uploading daily at 10:00 |
| `python uploader.py --setup` | Run interactive CLI setup wizard (add repos, URLs, author) |

---

## 📁 Project Structure

```
Automated Github uploader/
├── queue/                   # Drop files here to be committed
├── uploads/                 # Successfully committed files move here
├── logs/                    # Automated scheduler run logs
├── config.json              # Repository & author configuration
├── uploader.py              # Main Python engine
├── run_once.bat             # 1-click trigger to upload 1 file now
├── status.bat               # 1-click queue & history status check
├── setup_scheduler.bat      # 1-click Windows Task Scheduler manager
├── setup_scheduler.ps1      # PowerShell backend for Task Scheduler
├── upload_history.json      # Record of all uploaded files & commit hashes
└── test_uploader.py         # Unit & integration tests
```


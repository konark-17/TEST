"""
Unit and integration tests for Automated GitHub Uploader.
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta

import uploader


class TestUploader(unittest.TestCase):
    def setUp(self):
        # Create isolated test environment
        self.test_dir = Path(tempfile.mkdtemp(prefix="test_git_uploader_"))
        self.queue_dir = self.test_dir / "queue"
        self.uploads_dir = self.test_dir / "uploads"
        self.queue_dir.mkdir(parents=True)
        self.uploads_dir.mkdir(parents=True)

        self.original_base_dir = uploader.BASE_DIR
        self.original_config_path = uploader.CONFIG_PATH
        self.original_history_path = uploader.HISTORY_PATH

        uploader.BASE_DIR = self.test_dir
        uploader.CONFIG_PATH = self.test_dir / "config.json"
        uploader.HISTORY_PATH = self.test_dir / "upload_history.json"

        # Initialize mock git repo
        uploader.run_git_cmd(["init", "-b", "main"], cwd=self.test_dir)
        uploader.run_git_cmd(["config", "user.name", "TestUser"], cwd=self.test_dir)
        uploader.run_git_cmd(["config", "user.email", "test@example.com"], cwd=self.test_dir)

        self.config = {
            "queue_dir": "queue",
            "target_dir": "uploads",
            "remote_name": "origin",
            "branch": "main",
            "git_user_name": "TestUser",
            "git_user_email": "test@example.com",
            "commit_message_template": "Add {filename} [{date}]",
            "auto_push": False,
            "schedule_time": "10:00",
            "order": "alphabetical",
            "repos": {
                "TEST": {
                    "remote_url": "",
                    "branch": "main",
                    "target_dir": "uploads",
                }
            },
        }

    def tearDown(self):
        uploader.BASE_DIR = self.original_base_dir
        uploader.CONFIG_PATH = self.original_config_path
        uploader.HISTORY_PATH = self.original_history_path
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_queue_empty(self):
        files = uploader.get_queued_files(self.config)
        self.assertEqual(len(files), 0)
        result = uploader.upload_single_file(self.config, repo_name="TEST")
        self.assertFalse(result["success"])
        self.assertEqual(result["message"], "Queue is empty")

    def test_repo_selection_is_compulsory(self):
        # Create unassigned file directly in queue root
        (self.queue_dir / "unassigned.py").write_text("print('test')", encoding="utf-8")
        # Trying to upload without repo should fail
        result = uploader.upload_single_file(self.config, repo_name=None)
        self.assertFalse(result["success"])
        self.assertIn("Repository selection is compulsory", result["message"])

    def test_queue_sorting_alphabetical(self):
        # Create dummy files
        (self.queue_dir / "b_file.py").write_text("print('b')", encoding="utf-8")
        (self.queue_dir / "a_file.py").write_text("print('a')", encoding="utf-8")
        (self.queue_dir / "c_file.py").write_text("print('c')", encoding="utf-8")

        queued = uploader.get_queued_files(self.config)
        self.assertEqual([str(p) for p in queued], ["a_file.py", "b_file.py", "c_file.py"])

    def test_collision_resolution(self):
        # Create existing file in uploads
        (self.uploads_dir / "test.txt").write_text("existing", encoding="utf-8")
        unique_path = uploader.get_unique_target_path(self.uploads_dir, Path("test.txt"))
        self.assertEqual(unique_path.name, "test_1.txt")

    def test_upload_single_file_flow(self):
        # Place 2 files in queue under repo TEST
        test_queue = self.queue_dir / "TEST"
        test_queue.mkdir(parents=True, exist_ok=True)
        file1 = test_queue / "daily_solution1.py"
        file2 = test_queue / "daily_solution2.py"
        file1.write_text("# solution 1", encoding="utf-8")
        file2.write_text("# solution 2", encoding="utf-8")

        res1 = uploader.upload_single_file(self.config, repo_name="TEST")
        self.assertTrue(res1["success"])
        self.assertIn("daily_solution1.py", res1["file"])
        self.assertEqual(res1["files_remaining"], 1)

        # Verify moved
        self.assertFalse(file1.exists())
        self.assertTrue((self.uploads_dir / "daily_solution1.py").exists())

        # Verify git commit was created
        log_res = uploader.run_git_cmd(["log", "-n", "1", "--oneline"], cwd=self.test_dir)
        self.assertIn("Add daily_solution1.py", log_res.stdout)

        # Upload second file with custom date
        custom_dt = datetime(2026, 10, 15, 12, 0, 0)
        res2 = uploader.upload_single_file(self.config, repo_name="TEST", custom_date=custom_dt)
        self.assertTrue(res2["success"])
        self.assertEqual(res2["files_remaining"], 0)

        # Verify date in git
        log_res2 = uploader.run_git_cmd(["log", "-n", "1", "--format=%ad", "--date=iso"], cwd=self.test_dir)
        self.assertIn("2026-10-15", log_res2.stdout)

        # Check history recorded
        history = uploader.load_history()
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["filename"], "daily_solution1.py")
        self.assertEqual(history[1]["filename"], "daily_solution2.py")

    def test_upload_batch_spread(self):
        # Create 3 files in queue for TEST repo
        test_queue = self.queue_dir / "TEST"
        test_queue.mkdir(parents=True, exist_ok=True)
        for i in range(1, 4):
            (test_queue / f"spread_file_{i}.txt").write_text(f"content {i}", encoding="utf-8")

        # Run batch upload with spread
        uploader.upload_batch(self.config, repo_name="TEST", count=3, spread_days=True, days_back=3)

        history = uploader.load_history()
        self.assertEqual(len(history), 3)

        # Check that files were committed
        log_res = uploader.run_git_cmd(["log", "--oneline"], cwd=self.test_dir)
        self.assertIn("spread_file_1.txt", log_res.stdout)
        self.assertIn("spread_file_2.txt", log_res.stdout)
        self.assertIn("spread_file_3.txt", log_res.stdout)

    def test_multi_repo_support(self):
        # Configure multiple repos
        self.config["repos"] = {
            "leetcode": {
                "target_dir": "uploads/leetcode",
                "branch": "main",
            },
            "networking": {
                "target_dir": "uploads/networking",
                "branch": "main",
            }
        }
        # Place files under repo folders
        (self.queue_dir / "leetcode").mkdir(parents=True)
        (self.queue_dir / "leetcode" / "two_sum.cpp").write_text("// two sum", encoding="utf-8")
        (self.queue_dir / "networking").mkdir(parents=True)
        (self.queue_dir / "networking" / "sniffer.go").write_text("// sniffer", encoding="utf-8")

        # Test filtering
        leetcode_files = uploader.get_queued_files(self.config, repo_filter="leetcode")
        self.assertEqual(len(leetcode_files), 1)
        self.assertEqual(leetcode_files[0].name, "two_sum.cpp")

        # Upload leetcode file
        res = uploader.upload_single_file(self.config, repo_name="leetcode")
        self.assertTrue(res["success"])
        self.assertEqual(res["repo"], "leetcode")
        self.assertTrue((self.uploads_dir / "leetcode" / "two_sum.cpp").exists())

        # Check history has repo recorded
        history = uploader.load_history()
        self.assertEqual(history[-1]["repo"], "leetcode")


if __name__ == "__main__":
    unittest.main()

"""
Tests for Web Application APIs
"""

import unittest
from fastapi.testclient import TestClient
from web_app import app

client = TestClient(app)


class TestWebApp(unittest.TestCase):
    def test_index_page(self):
        response = client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("GitFlow", response.text)

    def test_status_endpoint(self):
        response = client.get("/api/status")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("config", data)
        self.assertIn("queue", data)
        self.assertIn("history", data)
        self.assertIn("scheduler", data)
        self.assertIn("stats", data)

    def test_logs_endpoint(self):
        response = client.get("/api/logs")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("logs", data)

    def test_queue_file_upload_and_delete(self):
        # Test uploading a file via multipart form
        file_content = b"print('Hello from web uploader test')"
        files = {"files": ("test_web_snippet.py", file_content, "text/plain")}
        data = {"repo": "default"}
        response = client.post("/api/queue/upload", files=files, data=data)
        self.assertEqual(response.status_code, 200)
        res_data = response.json()
        self.assertTrue(res_data["success"])
        self.assertIn("test_web_snippet.py", res_data["files"])

        # Test previewing the newly uploaded file
        prev_res = client.get("/api/queue/preview/test_web_snippet.py")
        self.assertEqual(prev_res.status_code, 200)
        self.assertIn("Hello from web uploader test", prev_res.json()["content"])

        # Test deleting the file
        del_res = client.delete("/api/queue/test_web_snippet.py")
        self.assertEqual(del_res.status_code, 200)
        self.assertTrue(del_res.json()["success"])

    def test_sync_status_endpoint(self):
        response = client.get("/api/sync/status")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("configured", data)
        self.assertIn("ahead", data)
        self.assertIn("behind", data)
        self.assertIn("status_text", data)


if __name__ == "__main__":
    unittest.main()

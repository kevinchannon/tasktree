"""Tests for hasher module."""

import unittest

from tasktree.hasher import hash_args, hash_task, make_cache_key


class TestHasher(unittest.TestCase):
    def test_hash_task_stability(self):
        """Test that task hashing is stable for same inputs."""
        hash1 = hash_task("echo hello", ["output.txt"], ".", [])
        hash2 = hash_task("echo hello", ["output.txt"], ".", [])
        self.assertEqual(hash1, hash2)

    def test_hash_task_changes_with_cmd(self):
        """Test that hash changes when command changes."""
        hash1 = hash_task("echo hello", ["output.txt"], ".", [])
        hash2 = hash_task("echo goodbye", ["output.txt"], ".", [])
        self.assertNotEqual(hash1, hash2)

    def test_hash_task_changes_with_outputs(self):
        """Test that hash changes when outputs change."""
        hash1 = hash_task("echo hello", ["output.txt"], ".", [])
        hash2 = hash_task("echo hello", ["different.txt"], ".", [])
        self.assertNotEqual(hash1, hash2)

    def test_hash_task_changes_with_working_dir(self):
        """Test that hash changes when working directory changes."""
        hash1 = hash_task("echo hello", ["output.txt"], ".", [])
        hash2 = hash_task("echo hello", ["output.txt"], "subdir", [])
        self.assertNotEqual(hash1, hash2)

    def test_hash_task_output_length(self):
        """Test that hash is 8 characters."""
        hash_val = hash_task("echo hello", ["output.txt"], ".", [])
        self.assertEqual(len(hash_val), 8)

    def test_hash_args_stability(self):
        """Test that args hashing is stable for same inputs."""
        args = {"environment": "production", "region": "us-west-1"}
        hash1 = hash_args(args)
        hash2 = hash_args(args)
        self.assertEqual(hash1, hash2)

    def test_hash_args_order_independent(self):
        """Test that args hash is independent of key order."""
        args1 = {"environment": "production", "region": "us-west-1"}
        args2 = {"region": "us-west-1", "environment": "production"}
        hash1 = hash_args(args1)
        hash2 = hash_args(args2)
        self.assertEqual(hash1, hash2)

    def test_hash_args_changes_with_values(self):
        """Test that hash changes when values change."""
        args1 = {"environment": "production"}
        args2 = {"environment": "staging"}
        hash1 = hash_args(args1)
        hash2 = hash_args(args2)
        self.assertNotEqual(hash1, hash2)

    def test_make_cache_key_without_args(self):
        """Test cache key creation without arguments."""
        task_hash = "abc12345"
        cache_key = make_cache_key(task_hash)
        self.assertEqual(cache_key, "abc12345")

    def test_make_cache_key_with_args(self):
        """Test cache key creation with arguments."""
        task_hash = "abc12345"
        args_hash = "def67890"
        cache_key = make_cache_key(task_hash, args_hash)
        self.assertEqual(cache_key, "abc12345__def67890")


if __name__ == "__main__":
    unittest.main()

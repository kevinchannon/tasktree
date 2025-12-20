import unittest
from unittest.mock import patch, call

from tasktree import tasks

class Tests(unittest.TestCase):
    @patch("subprocess.run")
    def test_loads_single_task(self, subproc_run_spy):
        task = {"hello": { "cmd": "echo hello"}}

        tasks.run(task)

        self.assertEqual([call("echo hello", shell=True)], subproc_run_spy.call_args_list)



if __name__ == '__main__':
    unittest.main()

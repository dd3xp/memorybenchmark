from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from memorybenchmark.ga_runtime import WSLJail


class WeekBoundary(unittest.TestCase):
    def test_native_jail_accepts_the_same_week_as_the_scientific_plan(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = root / "source"
            memory = root / "memory"
            support = root / "support"
            for path in (source, memory, support):
                path.mkdir()
            jail = WSLJail("Ubuntu", "/runtime", ("/runtime",))
            with patch.object(jail, "_run", return_value="/tmp/fixture"):
                command = jail.command(
                    source, memory, support, 604800, worker_filename="hermes_worker.py"
                )
                self.assertIn("604800", command)
                with self.assertRaises(ValueError):
                    jail.command(source, memory, support, 604801)


if __name__ == "__main__":
    unittest.main()

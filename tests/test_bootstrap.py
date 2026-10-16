import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]


def load_script(name, filename):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "new-home"

    def run_setup(self, *flags, environment=None):
        return subprocess.run([sys.executable, "-B", str(REPO / "scripts" / "bootstrap.py"), "--home", str(self.home), *flags], capture_output=True, text=True, env=environment)

    def test_default_plan_does_not_create_target_home(self):
        result = self.run_setup("--codex")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["mode"], "dry-run")
        self.assertFalse(self.home.exists())

    def test_new_home_starts_with_an_empty_registry(self):
        result = self.run_setup("--apply")
        self.assertEqual(result.returncode, 0, result.stderr)
        machine = self.home / "Developer" / "machine"
        self.assertEqual(json.loads((machine / "tools.json").read_text())["tools"], [])
        self.assertTrue((machine / "POLICY.md").is_file())
        self.assertTrue((self.home / "Developer" / "tools").is_dir())
        self.assertFalse((self.home / ".codex").exists())
        self.assertFalse((machine / "inventory.json").exists())

    def test_preserves_registry_and_existing_agent_text_and_is_idempotent(self):
        machine = self.home / "Developer" / "machine"
        machine.mkdir(parents=True)
        original = b'{"schema_version":1,"tools":[{"id":"existing-tool"}]}\n'
        (machine / "tools.json").write_bytes(original)
        (self.home / ".codex").mkdir()
        agent = self.home / ".codex" / "AGENTS.md"
        agent.write_text("Keep this existing agreement.\n")
        result = self.run_setup("--apply", "--codex")
        self.assertEqual(result.returncode, 0, result.stderr)
        count = len(list((machine / "changes").iterdir()))
        result = self.run_setup("--apply", "--codex")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((machine / "tools.json").read_bytes(), original)
        self.assertTrue(agent.read_text().startswith("Keep this existing agreement."))
        self.assertEqual(agent.read_text().count("<!-- BEGIN LOCAL MACHINE POLICY -->"), 1)
        self.assertEqual(len(list((machine / "changes").iterdir())), count)

    def test_conflict_stops_before_writing_any_other_files(self):
        machine = self.home / "Developer" / "machine"
        machine.mkdir(parents=True)
        (machine / "POLICY.md").write_text("An older local policy.\n")
        result = self.run_setup("--apply", "--codex")
        self.assertEqual(result.returncode, 2)
        self.assertEqual((machine / "POLICY.md").read_text(), "An older local policy.\n")
        self.assertFalse((machine / "tools.json").exists())
        self.assertFalse((self.home / ".codex").exists())
        self.assertFalse((self.home / "Developer" / "tools").exists())

    def test_explicit_update_backs_up_previous_policy(self):
        machine = self.home / "Developer" / "machine"
        machine.mkdir(parents=True)
        old = "An older local policy.\n"
        (machine / "POLICY.md").write_text(old)
        result = self.run_setup("--apply", "--update-managed")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((machine / "POLICY.md").read_bytes(), (REPO / "POLICY.md").read_bytes())
        backups = list((machine / "changes").glob("*-POLICY.md.bak"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), old)

    def test_invalid_registry_is_not_replaced(self):
        machine = self.home / "Developer" / "machine"
        machine.mkdir(parents=True)
        (machine / "tools.json").write_text("{not valid json")
        result = self.run_setup("--apply", "--update-managed")
        self.assertEqual(result.returncode, 2)
        self.assertEqual((machine / "tools.json").read_text(), "{not valid json")
        self.assertFalse((machine / "POLICY.md").exists())

    def test_rehearsal_home_does_not_use_real_codex_home_environment(self):
        trap = Path(self.temp.name) / "other-config"
        environment = dict(os.environ, CODEX_HOME=str(trap))
        result = self.run_setup("--apply", "--codex", environment=environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(trap.exists())
        self.assertTrue((self.home / ".codex" / "AGENTS.md").is_file())

    def test_nonempty_override_is_the_effective_codex_entry(self):
        config = self.home / ".codex"
        config.mkdir(parents=True)
        (config / "AGENTS.md").write_text("Base agreement.\n")
        override = config / "AGENTS.override.md"
        override.write_text("Temporary agreement.\n")
        result = self.run_setup("--apply", "--codex")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((config / "AGENTS.md").read_text(), "Base agreement.\n")
        self.assertIn("Temporary agreement.", override.read_text())
        self.assertIn("<!-- BEGIN LOCAL MACHINE POLICY -->", override.read_text())


class PortableMetadataTests(unittest.TestCase):
    def test_metadata_index_does_not_invent_installed_tools(self):
        module = load_script("portable_inventory", "refresh-inventory.py")
        snapshot = {"checked_at": "test", "package_managers": {"homebrew": {"status": "not_found_on_known_paths"}}}
        index = module.render_index({"tools": []}, snapshot)
        self.assertIn("空清单不表示没有安装工具", index)
        self.assertNotIn("ARTEX", index)
        self.assertNotIn("REA", index)

    def test_publish_check_rejects_machine_state_and_concrete_home_paths(self):
        module = load_script("publish_check", "check-repo.py")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "tools.json").write_text("{}")
            concrete = "/" + "Users/" + "example/" + "private-project"
            (root / "README.md").write_text(concrete)
            _, errors = module.check(root)
            self.assertTrue(any("machine state" in error for error in errors))
            self.assertTrue(any("user-home path" in error for error in errors))


if __name__ == "__main__":
    unittest.main()

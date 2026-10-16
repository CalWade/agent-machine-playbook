#!/usr/bin/env python3
"""Plan or apply user-level directory and policy setup using the standard library."""

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


REPO = Path(__file__).resolve().parent.parent
SOURCE_URL = "https://github.com/CalWade/agent-machine-playbook"
BEGIN = "<!-- BEGIN LOCAL MACHINE POLICY -->"
END = "<!-- END LOCAL MACHINE POLICY -->"


def atomic_write(path, data, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def merged_entry(existing, block):
    if (BEGIN in existing) != (END in existing):
        raise ValueError("Existing Agent entry has an incomplete policy marker")
    if existing.count(BEGIN) > 1 or existing.count(END) > 1:
        raise ValueError("Existing Agent entry has duplicate policy markers")
    if BEGIN in existing:
        start = existing.index(BEGIN)
        finish = existing.index(END, start) + len(END)
        return existing[:start] + block + existing[finish:]
    return (existing.rstrip() + "\n\n" if existing.strip() else "") + block + "\n"


def source_commit(repo):
    try:
        result = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5)
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def build_plan(repo, home, codex=False, codex_home=None, update_managed=False):
    machine = home / "Developer" / "machine"
    directories = [home / "Developer", machine, machine / "changes", home / "Developer" / "tools", home / "Developer" / "projects"]
    for path in directories:
        if path.exists() and not path.is_dir():
            raise ValueError("Expected a directory: " + str(path))
    registry = machine / "tools.json"
    if registry.exists():
        parsed = json.loads(registry.read_text(encoding="utf-8"))
        if not isinstance(parsed, dict) or not isinstance(parsed.get("tools"), list):
            raise ValueError("Existing tools.json is not a tool registry; preserve and repair it first")
    policy = (repo / "POLICY.md").read_bytes()
    provenance = json.dumps({"schema_version": 1, "repository": SOURCE_URL, "commit": source_commit(repo), "policy_sha256": hashlib.sha256(policy).hexdigest()}, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    managed = {
        "POLICY.md": (policy, 0o600),
        "refresh-inventory.py": ((repo / "scripts" / "refresh-inventory.py").read_bytes(), 0o700),
        "policy-source.json": (provenance, 0o600),
    }
    files = []
    conflicts = []
    preserved = []
    for name, (content, mode) in managed.items():
        target = machine / name
        exists = target.exists()
        if exists and target.read_bytes() == content:
            preserved.append(str(target))
        elif exists and not update_managed:
            conflicts.append(str(target))
        else:
            files.append({"path": target, "data": content, "mode": mode, "action": "update" if exists else "create"})
    for name in ["tools.json", "TOOLS.md"]:
        target = machine / name
        if target.exists():
            preserved.append(str(target))
        else:
            files.append({"path": target, "data": (repo / "templates" / name).read_bytes(), "mode": 0o600, "action": "create"})
    if codex:
        config_dir = codex_home or home / ".codex"
        override = config_dir / "AGENTS.override.md"
        target = override if override.is_file() and override.stat().st_size else config_dir / "AGENTS.md"
        existing = target.read_text(encoding="utf-8") if target.exists() else ""
        body = (repo / "templates" / "AGENT-ENTRY.md").read_text(encoding="utf-8").replace("{{MACHINE_DIR}}", str(machine))
        updated = merged_entry(existing, BEGIN + "\n" + body.rstrip() + "\n" + END)
        if existing == updated:
            preserved.append(str(target))
        else:
            files.append({"path": target, "data": updated.encode("utf-8"), "mode": 0o600, "action": "update" if target.exists() else "create"})
    return {"machine": machine, "directories": directories, "files": files, "conflicts": conflicts, "preserved": preserved}


def apply_plan(plan):
    if plan["conflicts"]:
        raise ValueError("Managed files differ; inspect the plan and use --update-managed if intended")
    for path in plan["directories"]:
        path.mkdir(parents=True, exist_ok=True)
    changes = []
    stamp = datetime.datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%f")
    for index, item in enumerate(plan["files"]):
        path = item["path"]
        backup = None
        if path.exists():
            backup = plan["machine"] / "changes" / (stamp + "-" + str(index) + "-" + path.name + ".bak")
            atomic_write(backup, path.read_bytes())
        atomic_write(path, item["data"], item["mode"])
        changes.append({"action": item["action"], "path": str(path), "backup": str(backup) if backup else None})
    if changes:
        record = {"timestamp": datetime.datetime.now().astimezone().isoformat(), "source": SOURCE_URL, "changes": changes, "preserved": plan["preserved"]}
        atomic_write(plan["machine"] / "changes" / (stamp + "-bootstrap.json"), json.dumps(record, ensure_ascii=False, indent=2).encode("utf-8") + b"\n")
    return changes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="Apply the displayed plan; default is read-only")
    mode.add_argument("--dry-run", action="store_true", help="Display the plan without writing files (default)")
    parser.add_argument("--home", type=Path, help="Explicit target user home, also useful for an isolated rehearsal")
    parser.add_argument("--codex", action="store_true", help="Add a marked policy pointer to the effective Codex global instructions")
    parser.add_argument("--codex-home", type=Path, help="Explicit Codex configuration directory")
    parser.add_argument("--update-managed", action="store_true", help="Allow differing managed files to be updated with backups")
    args = parser.parse_args()
    home = (args.home or Path.home()).expanduser().resolve()
    config = args.codex_home
    if config is None and args.home is None and os.environ.get("CODEX_HOME"):
        config = Path(os.environ["CODEX_HOME"])
    config = config.expanduser().resolve() if config else home / ".codex"
    try:
        plan = build_plan(REPO, home, args.codex, config, args.update_managed)
        summary = {"mode": "apply" if args.apply else "dry-run", "machine_directory": str(plan["machine"]), "create_directories": [str(path) for path in plan["directories"] if not path.exists()], "file_changes": [{"action": item["action"], "path": str(item["path"])} for item in plan["files"]], "preserved": plan["preserved"], "conflicts": plan["conflicts"]}
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        if plan["conflicts"]:
            parser.exit(2, "Managed files differ; nothing was written. Review before using --update-managed.\n")
        if args.apply:
            changes = apply_plan(plan)
            print("Applied " + str(len(changes)) + " file changes. Existing machine registry was preserved.")
    except (OSError, ValueError) as error:
        parser.exit(2, "Setup stopped: " + str(error) + "\n")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Refresh local installation metadata and render the tool index; installs nothing."""

import argparse
import concurrent.futures
import datetime
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import tempfile


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path.home() / "Developer" / "machine" if SCRIPT_DIR.name == "scripts" else SCRIPT_DIR


def expanded(value):
    return str(Path(value).expanduser())


def atomic_write(path, content):
    handle, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(content)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def manager_command(name, fallback=None):
    found = shutil.which(name)
    if not found and fallback and Path(expanded(fallback)).is_file():
        found = expanded(fallback)
    return found


def run_metadata(command):
    environment = dict(os.environ)
    environment.update(HOMEBREW_NO_AUTO_UPDATE="1", npm_config_update_notifier="false", UV_NO_PROGRESS="1")
    try:
        process = subprocess.run(command, capture_output=True, text=True, timeout=45, env=environment)
    except (OSError, subprocess.TimeoutExpired) as error:
        return None, type(error).__name__
    if process.returncode:
        return None, "metadata command exited with code " + str(process.returncode)
    return process.stdout, None


def homebrew_metadata():
    command = manager_command("brew", "/opt/homebrew/bin/brew")
    if not command:
        return {"status": "not_found_on_known_paths"}
    output, error = run_metadata([command, "info", "--json=v2", "--installed"])
    if error:
        return {"status": "unavailable", "reason": error}
    try:
        info = json.loads(output)
        formulas = []
        for item in info.get("formulae", []):
            installed = item.get("installed") or []
            formulas.append({
                "name": item.get("name"),
                "versions": [record.get("version") for record in installed if isinstance(record, dict)],
                "installed_on_request": any(record.get("installed_on_request") for record in installed if isinstance(record, dict)),
                "dependencies": item.get("dependencies", []),
                "description": item.get("desc"),
            })
        casks = []
        for item in info.get("casks", []):
            casks.append({"name": item.get("token"), "installed_versions": item.get("installed"), "description": item.get("desc")})
        return {"status": "ok", "formulas": formulas, "casks": casks}
    except (TypeError, ValueError):
        return {"status": "unavailable", "reason": "metadata JSON could not be parsed"}


def npm_metadata():
    command = manager_command("npm", "/opt/homebrew/bin/npm")
    if not command:
        return {"status": "not_found_on_known_paths"}
    output, error = run_metadata([command, "list", "--global", "--depth=0", "--json"])
    if error:
        return {"status": "unavailable", "reason": error}
    try:
        info = json.loads(output)
        return {"status": "ok", "packages": [{"name": name, "version": item.get("version")} for name, item in sorted(info.get("dependencies", {}).items())]}
    except (TypeError, ValueError):
        return {"status": "unavailable", "reason": "metadata JSON could not be parsed"}


def uv_metadata():
    command = manager_command("uv", "~/.local/bin/uv")
    if not command:
        return {"status": "not_found_on_known_paths"}
    output, error = run_metadata([command, "tool", "list"])
    if error:
        return {"status": "unavailable", "reason": error}
    packages = []
    for line in output.splitlines():
        match = re.match(r"^([A-Za-z0-9_.-]+)\s+v([A-Za-z0-9_.+!-]+)(?:\s|$)", line)
        if match:
            packages.append({"name": match.group(1), "version": match.group(2)})
    return {"status": "ok", "packages": packages}


def pipx_metadata():
    command = manager_command("pipx")
    if not command:
        return {"status": "not_found_on_known_paths"}
    output, error = run_metadata([command, "list", "--json"])
    if error:
        return {"status": "unavailable", "reason": error}
    try:
        info = json.loads(output)
        packages = []
        for item in info.get("venvs", {}).values():
            package = item.get("metadata", {}).get("main_package", {})
            packages.append({"name": package.get("package"), "version": package.get("package_version")})
        return {"status": "ok", "packages": packages}
    except (TypeError, ValueError):
        return {"status": "unavailable", "reason": "metadata JSON could not be parsed"}


def path_metadata(registry):
    result = []
    for tool in registry["tools"]:
        paths = []
        values = [tool.get("install_path")]
        entry = tool.get("entry", {})
        for key in ["command", "control_script", "cli_path", "executable"]:
            value = entry.get(key)
            values.append(value[0] if isinstance(value, list) and value else value)
        for value in values:
            if not isinstance(value, str) or not Path(value).expanduser().is_absolute():
                continue
            path = Path(value).expanduser()
            try:
                paths.append({"path": str(path), "exists": path.exists(), "resolved": str(path.resolve()) if path.exists() else None})
            except OSError:
                paths.append({"path": str(path), "exists": None, "reason": "path_metadata_unavailable"})
        commands = []
        for name in entry.get("commands", []):
            commands.append({"name": name, "path": shutil.which(name)})
        result.append({"id": tool["id"], "paths": paths, "path_commands": commands})
    return result


def native_metadata(registry):
    result = []
    for tool in registry["tools"]:
        path = tool.get("install_path", "")
        if not path.endswith(".app"):
            continue
        info = Path(path).expanduser() / "Contents" / "Info.plist"
        if info.is_file():
            try:
                with info.open("rb") as stream:
                    data = plistlib.load(stream)
                result.append({"id": tool["id"], "version": data.get("CFBundleShortVersionString"), "build": data.get("CFBundleVersion")})
            except (OSError, ValueError):
                result.append({"id": tool["id"], "status": "metadata_unavailable"})
    return result


def cell(value):
    return str(value or "未登记").replace("|", "\\|").replace("\n", " ")


def render_index(registry, snapshot):
    labels = {"unverified": "未验证", "workflow": "已验证所述流程", "basic": "已验证基础项", "metadata": "安装元数据或路径", "documented": "已核对说明"}
    lines = ["# 本机工具索引", "", "生成时间：" + snapshot["checked_at"] + "。", "", "先阅读 [本机安装与目录管理原则](POLICY.md)。工具用途及验证范围以 tools.json 为主，安装元数据和路径快照见 inventory.json。本页由 refresh-inventory.py 生成。", "", "## 按用途找工具", ""]
    if not registry["tools"]:
        lines += ["本机工具用途尚未登记。空清单不表示没有安装工具；参考下方采集结果，按实际任务核实并补充。", ""]
    else:
        lines += ["| 工具 | 用途 | 入口 | 验证范围 |", "| --- | --- | --- | --- |"]
        for tool in registry["tools"]:
            entry = tool.get("entry", {})
            invoke = entry.get("url") or entry.get("command") or entry.get("control_script") or entry.get("cli_path") or entry.get("executable") or entry.get("readme") or entry.get("commands") or entry.get("service_name") or tool.get("install_path")
            if isinstance(invoke, list):
                invoke = " ".join(invoke)
            verification = tool.get("verification", {})
            checked = labels.get(verification.get("level", "unverified"), "未验证") + "；" + str(verification.get("date") or "无日期") + "；" + str(verification.get("scope") or "未登记范围")
            lines.append("| " + " | ".join(cell(value) for value in [tool.get("name", tool["id"]), tool.get("purpose"), "`" + str(invoke or "未登记") + "`", checked]) + " |")
    lines += ["", "## 包管理器快照", ""]
    for key, data in snapshot["package_managers"].items():
        if data["status"] != "ok":
            lines.append("- " + key + "：" + data["status"] + ("（" + data.get("reason", "") + "）" if data.get("reason") else ""))
        elif key == "homebrew":
            formulas, casks = data.get("formulas", []), data.get("casks", [])
            lines.append("- Homebrew：" + str(len(formulas)) + " 个 formula、" + str(len(casks)) + " 个 cask，包括依赖，不是全部独立工具。")
            requested = sorted(item["name"] for item in formulas if item.get("installed_on_request"))
            if requested:
                lines.append("- Homebrew 标记为直接安装的 formula：" + "、".join(requested) + "。")
            if casks:
                lines.append("- Homebrew cask：" + "、".join(sorted(str(item["name"]) for item in casks)) + "。")
        else:
            packages = data.get("packages", [])
            lines.append("- " + key + "：" + ("、".join(str(item["name"]) + " " + str(item.get("version") or "") for item in packages) if packages else "未发现由此管理器登记的工具") + "。")
    lines += ["", "## 使用与维护", "", "快照仅代表这次采集到的安装元数据和路径，不等于功能验收，也不代表当前 Agent 已连接 MCP。", "", "更新 tools.json 后运行同目录 refresh-inventory.py。本机清单和快照保留在本机，不提交到通用规则仓库。", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--machine-dir", type=Path, default=ROOT, help="Machine state directory; never defaults to the public repository")
    args = parser.parse_args()
    root = args.machine_dir.expanduser().resolve()
    try:
        registry = json.loads((root / "tools.json").read_text(encoding="utf-8"))
        if not isinstance(registry, dict) or not isinstance(registry.get("tools"), list):
            raise ValueError("Invalid tool registry")
    except (OSError, ValueError) as error:
        parser.exit(2, "Read registry failed; initialize or repair it first: " + str(error) + "\n")
    ids = [tool["id"] for tool in registry["tools"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate tool ids in tools.json")
    jobs = {"homebrew": homebrew_metadata, "npm_global": npm_metadata, "uv_tools": uv_metadata, "pipx_tools": pipx_metadata}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = {name: executor.submit(function) for name, function in jobs.items()}
        managers = {name: future.result() for name, future in futures.items()}
    snapshot = {
        "schema_version": 1,
        "checked_at": datetime.datetime.now().astimezone().isoformat(),
        "scope": "Package metadata and registered paths only; no secret or business-file content and no workflow verification.",
        "package_managers": managers,
        "registered_paths": path_metadata(registry),
        "registered_native_applications": native_metadata(registry),
    }
    index = render_index(registry, snapshot)
    atomic_write(root / "inventory.json", json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n")
    atomic_write(root / "TOOLS.md", index)
    print(json.dumps({"registry_entries": len(ids), "manager_status": {key: value["status"] for key, value in managers.items()}, "written": [str(root / "TOOLS.md"), str(root / "inventory.json")]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

# 在新电脑初始化和在已有电脑升级

## 新电脑

1. 阅读仓库规则，确认当前用户目录和操作系统。
2. 将仓库放到独立目录，例如 `~/Developer/projects/agent-machine-playbook`。目录已有内容时先检查，不直接覆盖或强制重新克隆。
3. 运行 `python3 scripts/bootstrap.py`，查看将创建或保留的文件。默认不写文件。
4. 在用户要求的范围内运行 `python3 scripts/bootstrap.py --apply`。
5. 运行 `python3 scripts/refresh-inventory.py`，采集已有安装元数据并生成本机索引。
6. 按任务需要完善本机 `tools.json` 的用途和验证范围。包管理器快照不能替代功能检查。

脚本需要 Python 3.9+；没有时可让 Agent 按目录说明和模板完成等价文件操作。不要为了应用本规范而先安装全部运行时或大型软件。

## Codex 或其他 Agent

需要 Codex 全局入口时，计划与应用命令都加 `--codex`。默认使用实际 `CODEX_HOME` 或 `~/.codex`；非空的 `AGENTS.override.md` 优先。脚本仅维护带标记的规范入口块，保留原来的其他指令，并备份变动前的文件。

使用 `--home` 指定演练用户目录时，Codex 默认也放在这个演练目录下；仅在显式设置 `--codex-home` 后使用别的位置，避免演练误改真实入口。

其他 Agent 按自己的全局规则入口设置 [入口模板](../templates/AGENT-ENTRY.md)。不同客户端不共享 MCP 注册和运行中的工具列表。读取规范也不意味着所有本机工具自动获得调用授权。

## 已有电脑升级

已有工具登记、阅读索引和安装快照始终保留。仓库管理的 `POLICY.md`、采集脚本或来源记录有差异时，先检查计划：

```sh
python3 scripts/bootstrap.py --update-managed --codex
python3 scripts/bootstrap.py --apply --update-managed --codex
python3 scripts/refresh-inventory.py
```

更新会备份旧的受管理文件，记录来源指纹和本次变更。它不会把模板中的空工具清单覆盖到已有清单上，也不会自动更新应用、依赖或 MCP 绑定。

如果现有 `tools.json` 无法解析，先保留并修复该登记；脚本会停止，不通过重建空文件掩盖问题。

## 来源与恢复

`~/Developer/machine/policy-source.json` 记录仓库地址、可用时的提交号和原则文件的 SHA-256。`changes` 保存初始化记录及被更改文件的备份。

恢复前先核对文件是否有后续用户修改；只恢复需要的旧副本，或移除带标记的 Agent 入口。不要用整目录覆盖的方式恢复机器状态。新增目录可以继续作为普通目录使用，初始化不改变已有应用安装。

# Agent 本机环境管理手册

把这个仓库交给新电脑上的 Agent，先建立有条理的目录和工具登记，再按实际任务安装工具。已有电脑也可以按同一规则逐项整理。

仓库保存通用原则、目录模板和初始化脚本；每台电脑的实际工具、配置和验证记录保存在它自己的 `~/Developer/machine`。

## 直接交给 Agent

把以下要求连同本仓库链接一起发给 Agent：

> 先阅读仓库的 README.md、AGENTS.md、POLICY.md 和 docs/BOOTSTRAP.md。检查这台机器的系统、已有目录和工具，给出初始化计划，随后在我授权的范围内部署目录规范、工具登记和当前 Agent 的读取入口。复用已有依赖，保护已有配置，完成必要验证并记录实际状态。按我的实际任务安装工具；不要照搬其他电脑的软件清单，也不要直接搬动现有运行环境。

仓库地址：<https://github.com/CalWade/agent-machine-playbook>。

## 快速开始

需要 Git 和 Python 3.9 或更高版本。缺少时，Agent 可以先按文档用自己的文件工具创建目录和复制模板，再只补充实际需要的运行环境。

```sh
git clone https://github.com/CalWade/agent-machine-playbook.git ~/Developer/projects/agent-machine-playbook
cd ~/Developer/projects/agent-machine-playbook

# 默认只展示计划，不写文件
python3 scripts/bootstrap.py

# 确认计划符合当前任务后应用
python3 scripts/bootstrap.py --apply

# 只读采集本机安装元数据，刷新工具索引
python3 scripts/refresh-inventory.py
```

如果使用 Codex，并且希望它在涉及本机环境的任务中读取规范，可在初始化时显式增加 `--codex`：

```sh
python3 scripts/bootstrap.py --codex
python3 scripts/bootstrap.py --apply --codex
```

其他客户端使用自己的全局指令入口，按 [全局入口模板](templates/AGENT-ENTRY.md) 设置。不要假设所有客户端会自动读取同一个文件。

已有机器的规则或采集脚本与仓库不同，初始化会报告冲突，保留原文件。确实要更新这些受管理文件时，先看计划，再使用 `--update-managed`；已有工具登记和采集结果不会被空白模板覆盖。

## 目录

```text
本仓库                         ~/Developer/machine
├── README.md                 ├── POLICY.md          部署的原则副本
├── AGENTS.md                 ├── tools.json         本机工具主登记
├── POLICY.md                 ├── TOOLS.md           本机阅读索引
├── docs/                     ├── inventory.json     本机安装快照
├── templates/                ├── refresh-inventory.py
├── scripts/                  ├── policy-source.json 规则来源和指纹
└── tests/                    └── changes/           本机变更与备份
```

- [长期原则](POLICY.md)：归属、依赖隔离、登记、验证、迁移和恢复。
- [目录说明](docs/DIRECTORIES.md)：新工具、项目、应用数据和缓存分别放哪里。
- [初始化和升级](docs/BOOTSTRAP.md)：新电脑、已有电脑、Codex 入口与恢复步骤。
- [工具登记](docs/REGISTRY.md)：记录用途与验证范围，区分安装和当前会话可调用。

## 维护仓库

通用规则在本仓库修改；机器状态在本机登记。公开提交前运行：

```sh
python3 -B -m unittest discover -s tests
python3 scripts/check-repo.py
git diff --check
```

初始化脚本仅使用 Python 标准库，不下载软件、不修改 PATH、不开放端口、不授予 MCP 权限。只读采集会查询已有的包管理器；没有某个管理器时记录该条件，不替用户安装它。

当前自动化验证覆盖本机文件初始化、保留已有状态、重复执行和仓库内容检查。具体应用的安装与运行能力由实际任务另行验收。

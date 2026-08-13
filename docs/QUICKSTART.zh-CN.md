# Scheme C 复现快速开始

本仓库分成两个访问层级。必须把它们分开说明，才能避免公开源代码对第三方数据
作出不真实的承诺。

## A. 公开审计——不需要 benchmark 数据

需要 Windows 10/11 和 CPython 3.10.11。如果直接下载仓库 ZIP，则不强制安装
Git。

```powershell
git clone https://github.com/hanzohanzhe/SCHEME-C-PhD-Reproduction.git
cd SCHEME-C-PhD-Reproduction
py -3.10 reproduction-tools/verify_repository.py
```

预期结果是完整性工具确认冻结文件和 6 个权威历史哈希。此后可以检查原始
PSM/CEM、历史启动器、参考结果、日志、授权和溯源记录。

这一级别**不会运行数值模型**。

## B. 完整数值复现——需要 benchmark 数据

除 Windows 和 Python 外，请预留至少 5 GB 空间，并取得准确的
`force-uk-benchmark-2025-v1.zip`。它的固定 SHA-256 为：

```text
0bc3a78d535fbb6198ee16d708343e6d70a01de76fa2e5459ffb27cebd2cb672
```

有两种取得方式：

1. 获得 `hanzohanzhe/FORCE-UK-Benchmark-Data` 的访问权，安装并登录 GitHub
   CLI（`gh`），然后双击 `install-scheme-c.cmd`；
2. 通过有授权的渠道取得固定 ZIP，然后运行：

```powershell
powershell -ExecutionPolicy Bypass -File reproduction-tools/install-scheme-c.ps1 `
  -ArchivePath "D:\path\force-uk-benchmark-2025-v1.zip"
```

安装器会核验冻结源代码、建立 `.venv`、核对数据哈希、创建一次性 `work/`
目录并挂载历史代码使用的 `F:` 天气路径。它不会修改 `original-model/`、
`external-storage/`、`original-drivers/` 或 `reference-results/`。

如果 `F:` 已经装有无关文件，请停止；应使用能够安全分配该盘符的 Windows
电脑或虚拟机。

先运行一年：

```powershell
powershell -ExecutionPolicy Bypass -File reproduction-tools/run-scheme-c.ps1 `
  -Scenario existing_decarb_base -StartYear 2025 -EndYear 2025
```

一年成功后，再运行五个十年情景：

```powershell
powershell -ExecutionPolicy Bypass -File reproduction-tools/run-thesis-benchmark.ps1
```

## 当前公开安装边界

源代码仓库是公开的，但准确的英国研究数据包仍是单独管理、逐对象授权的
Release，匿名用户不能直接下载。因此当前公开版本支持匿名代码审计和结果检查；
完整数值复现仍需要数据访问权。这是数据访问限制，不是隐藏的代码依赖。

结果解释见 [RESULTS_GUIDE.md](RESULTS_GUIDE.md)；科学证据边界见
[PROVENANCE.md](PROVENANCE.md) 和 [VALIDATION_STATUS.md](VALIDATION_STATUS.md)。

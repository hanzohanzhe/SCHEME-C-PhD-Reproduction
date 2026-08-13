# Scheme C 1000 TWh——博士论文原始模型复现档案

这个公开仓库保存了 2026 年 7 月 18–19 日运行 1000 TWh 虚拟储能池情景时
使用的原始 Scheme C 研究模型。它的用途是复现、核查 Hanzhe Xing 博士论文
相关的数值结果。它不是后来模块化的 FORCE 前端和平台。

最短安装步骤见 [`docs/QUICKSTART.zh-CN.md`](docs/QUICKSTART.zh-CN.md)。公开访问
包括源代码、文档和保留的紧凑结果；真正运行数值模型还需要单独管理的英国
benchmark 压缩包。公开仓库访问权不等于该数据包的访问权。

## 仓库里分别是什么

| 目录 | 内容 | 是否直接修改 |
| --- | --- | --- |
| `original-model/` | 原始 PSM/CEM 研究代码 | 不允许；需要修改时另开版本 |
| `external-storage/` | 原始 Scheme C 储能扩张上限模块 | 不允许 |
| `original-drivers/` | 2026-07-18/19 使用的批量启动脚本 | 不允许 |
| `reference-results/` | 五个保留情景的紧凑结果与运行日志 | 不允许 |
| `benchmark-data-metadata/` | 英国数据包的来源、授权和哈希 | 随数据包另行管理 |
| `reproduction-tools/` | 新增的安装、数据装配和运行工具 | 可通过 Git 正常维护 |
| `docs/` | 溯源、结果和版本管理说明 | 可通过新提交维护 |

原始文件保留原始文件名、编码、Windows 路径和当时的研究代码结构。辅助工具
不会改动这些文件，而是在 `work/` 下复制一套临时运行目录。

## 这套原始模型做了什么

- 英国被建模为没有内部输电约束的单节点系统；
- interconnector 是来自系统边界外部的进口报价，不是英国境内输电线路；
- PSM 每个完整年份出清 17,520 个半小时，以 bid-at-cost 方式让新能源、
  火电、储能和进口电连续竞争；
- 原始模型不含机组启停、爬坡、最低出力和最短启停时间约束；
- CEM 每年读取 PSM 结果，然后依次执行 agent 投资、planning pipeline、
  风光扩张上限和储能扩张上限，再进入下一年；
- `1e9 MWh`（1000 TWh）和 `1e9 MW` 是为了观察循环频率谱而设置的非约束
  虚拟储能池，不是模型报告的实际装机储能；
- 历史运行使用 `scheme_c` 储能扩张信用规则和 expected-value 项目成功模式。

## 需要安装什么

- Windows 10/11；
- Git（也可以直接下载源码 ZIP）；
- 已登录数据仓库的 GitHub CLI（`gh`），或者已在本机取得固定的英国 benchmark ZIP；
- CPython 3.10.11，并可通过 `py -3.10` 调用；
- 短期运行至少预留约 5 GB；
- 完整 generation trace、checkpoint 和十年结果需要更多空间。

完整五情景十年复现可能运行一天到几天。第一次请只跑一年。

## 快速安装

克隆或下载本仓库后，已获数据访问权的用户可双击 `install-scheme-c.cmd`。
它会依次核验冻结档案、创建锁定的 Python 环境、下载或接收固定数据包、建立
一次性运行目录，并挂载原始模型使用的天气路径。

如果数据 ZIP 已经在电脑上，请运行：

```powershell
powershell -ExecutionPolicy Bypass -File reproduction-tools/install-scheme-c.ps1 `
  -ArchivePath "D:\path\force-uk-benchmark-2025-v1.zip"
```

匿名公开用户可以下载代码并完成完整性核验，但在取得单独管理的数据包之前，
不能完成数值复现。两种访问级别和预期结果见
[`docs/QUICKSTART.zh-CN.md`](docs/QUICKSTART.zh-CN.md)。

## 手工安装

在仓库根目录打开 PowerShell：

```powershell
# 1. 核对原始文件没有变化
py -3.10 reproduction-tools/verify_repository.py

# 2. 创建 Python 3.10 环境
powershell -ExecutionPolicy Bypass -File reproduction-tools/create-environment.ps1

# 3. 下载英国 benchmark 数据并建立临时运行目录
powershell -ExecutionPolicy Bypass -File reproduction-tools/prepare-data.ps1

# 4. 把仓库内的天气目录映射为原始代码使用的 F: 盘路径
powershell -ExecutionPolicy Bypass -File reproduction-tools/mount-weather-drive.ps1
```

数据工具会从私有仓库 `hanzohanzhe/FORCE-UK-Benchmark-Data` 下载
`force-uk-benchmark-2025-v1.zip`，核对固定 SHA-256，然后在 `work/` 下解压，
并把原始模型需要的文件名装配到临时模型目录。`original-model/` 不会改变。

如果电脑上已有 842 MB 的 ZIP：

```powershell
powershell -ExecutionPolicy Bypass -File reproduction-tools/prepare-data.ps1 `
  -ArchivePath "D:\path\force-uk-benchmark-2025-v1.zip"
```

原始代码写死了 `F:\newfinalweather`。如果 `F:` 已经包含哈希完全一致的两份
天气文件，辅助程序会验证后直接复用，不会修改它。如果 `F:` 用于其他用途，请
停止，不要覆盖；应在可以安全分配 `F:` 的 Windows 电脑或虚拟机中复现。直接
修改原始路径会形成新的模型版本，不再是严格原始复现。

## 推荐的第一次试运行

先运行 2025 一个完整年份：

```powershell
powershell -ExecutionPolicy Bypass -File reproduction-tools/run-scheme-c.ps1 `
  -Scenario existing_decarb_base -StartYear 2025 -EndYear 2025
```

结果写入 `outputs/`，不会污染原始代码目录。运行前会记录 Git commit、数据包
哈希、情景和环境声明。

可选情景：

- `existing_decarb_base`：03，现有脱碳基准；
- `subsidy_as_usual`：07，补贴照常延续；
- `governmental_target`：08，政府目标；
- `base`：05，不含容量市场的基准；
- `base_with_cm`：06，含容量市场的基准。

## 完整复现 2025–2034

一年测试成功后运行：

```powershell
powershell -ExecutionPolicy Bypass -File reproduction-tools/run-thesis-benchmark.ps1
```

辅助程序默认顺序运行五个情景，避免资源争用。历史 7 月 18 日运行先并行运行
03 和 07，再运行 08。原始 launcher 已保留在 `original-drivers/`，但它包含
原电脑的目录搜索逻辑，因此不作为新电脑上的推荐入口。

## 应该比较哪些结果

至少比较：

1. `system_cost_history_*.csv`；
2. `capacity_history_*.csv`；
3. `thermal_capacity_history_*.csv`；
4. `investment_summary_*.csv`；
5. 日志中的情景声明、年份和成功返回码。

参考结果解释见 `docs/RESULTS_GUIDE.md`。逐字节一致是最强复现证据。如果新环境
出现差异，不要覆盖参考文件；应记录 Python/依赖版本、第一个出现差异的年份和
字段，再判断是环境差异还是模型问题。

## 版权、数据和版本

代码采用 Apache-2.0；仓库文档采用 CC BY 4.0。英国和第三方研究数据保留各自
授权条件，通过单独的私有数据 Release 分发，详见
`benchmark-data-metadata/SOURCE_REGISTER.md`。

版权所有者为 Hanzhe Xing（`hx279`）；Stuart Scott 与 John Miles 作为贡献导师
和顾问署名致谢。

今后快照以 Git commit 和不可移动的 annotated tag 为准，不再把 ZIP 当作版本
身份。首个科学版本标签为 `scheme-c-1000twh-2026-07-18_19`。

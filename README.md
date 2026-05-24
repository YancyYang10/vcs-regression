# IC Verification Regression Simulation Script

IC 验证回归仿真自动化脚本，支持并行执行、失败重试、覆盖率收集和 HTML 报告生成。

## 功能特性

- **并行执行**：多任务并行仿真，提高验证效率
- **失败重试**：支持配置重试次数，减少误判
- **超时控制**：小时为单位，易于人工识别
- **覆盖率收集**：支持 VCS 覆盖率收集和 URG 报告生成
- **结果判定**：基于 UVM 报告摘要的正则匹配
- **HTML 报告**：自动生成详细的回归测试报告，并在运行期间实时刷新进度
- **统一日志**：所有过程日志统一写入 `logging.txt`，按追加模式保留历史记录
- **命令预览**：支持只查看将要执行的编译和仿真命令
- **执行模式**：支持完整回归、只编译、只仿真

## 目录结构

```
regression/
├── regr_run.py          # 主入口脚本
├── regress.cfg          # 默认配置文件
├── case.lst             # 默认测试用例列表
└── regr/                # 核心模块
    ├── __init__.py
    ├── config.py        # 配置管理
    ├── case_parser.py   # 测试用例解析
    ├── compiler.py      # 编译管理
    ├── executor.py      # 仿真执行
    ├── result_checker.py# 结果判定
    ├── reporter.py      # 报告生成
    └── utils.py         # 工具函数
```

## 快速开始

```bash
# 进入仿真目录（需包含 Makefile）
cd /path/to/simulation

# 运行回归测试
python3 /path/to/regression/regr_run.py -c regress.cfg -l case.lst -j 4
```

## 配置文件

配置文件默认为 `regress.cfg`，采用 INI 格式：

```ini
# 并行配置
jobs = 4              # 并行任务数
retry = 1             # 失败重试次数
timeout = 1           # 单次仿真超时（小时）

# 测试用例配置
case_list = case.lst  # 测试用例列表文件
pl = UVM_MEDIUM       # UVM 打印等级

# 覆盖率配置
coverage = true
coverage_args = -cm line+cond+branch+fsm+tgl+assert
urg_report = false

# 结果判定（正则表达式）
fail_keywords = UVM_FATAL\s*:\s*[1-9]\d*|UVM_ERROR\s*:\s*[1-9]\d*

# 全局参数
global_args =
```

### UVM 打印等级

| 等级 | 说明 |
|------|------|
| `UVM_LOW` | 仅显示关键信息 |
| `UVM_MEDIUM` | 默认级别，显示常规信息 |
| `UVM_HIGH` | 显示详细信息 |
| `UVM_FULL` | 显示完整信息 |
| `UVM_DEBUG` | 显示调试信息 |

## 测试用例列表

测试用例列表文件每行一个测试用例，格式：

```
# 格式: case_name [mode] [times] [seed] [extra_args]
test_basic
test_write_read rtl_sim 10
test_reset rtl_sim 1 12345
test_stress rtl_sim 5 - DEBUG=1
```

| 字段 | 说明 | 默认值 |
|------|------|--------|
| case_name | 测试用例名称 | 必填 |
| mode | 仿真模式 | `rtl_sim` |
| times | 重复次数 | 1 |
| seed | 随机种子 | 自动生成 |
| extra_args | 额外参数 | 无 |

## 命令行参数

```
usage: regr_run.py [options]

配置文件:
  -c CONFIG, --config CONFIG
                        配置文件路径 (默认: regress.cfg)

文件路径:
  -l CASE_LIST, --case-list CASE_LIST
                        测试用例列表文件 (默认: case.lst)
  --target TARGET       Make 目标 (默认: sim)

执行选项:
  -j JOBS, --jobs JOBS  并行任务数 (默认: 1)
  -r RETRY, --retry RETRY
                        失败重试次数 (默认: 0)
  -t TIMEOUT, --timeout TIMEOUT
                        单次仿真超时，单位：小时 (默认: 1)
  --pl {UVM_LOW,UVM_MEDIUM,UVM_HIGH,UVM_FULL,UVM_DEBUG}
                        UVM 打印等级 (默认: UVM_MEDIUM)

覆盖率选项:
  --coverage            启用覆盖率收集 (默认: 启用)
  --no-coverage         禁用覆盖率收集
  --coverage-args ARGS  VCS 覆盖率参数
  --urg                 生成 URG 覆盖率报告

结果判定:
  --fail-keywords PATTERN
                        失败关键字正则表达式
  --pass-keywords PATTERN
                        成功关键字正则表达式

其他:
  -g ARGS, --global-args ARGS
                        全局 Make 参数
  --dry-run             只打印编译和仿真命令，不实际执行
  --show-commands       只显示编译和仿真命令（等价于 --dry-run）
  --compile-only        只编译，不执行仿真
  --skip-compile        跳过编译，直接执行仿真
  --sim-only            只仿真（等价于 --skip-compile）
  -d, --debug           启用调试模式（输出 HTML 报告更新错误等调试信息）
```

## 使用示例

```bash
# 基本用法
python3 regr_run.py -c regress.cfg -l case.lst

# 4 并行任务，失败重试 2 次
python3 regr_run.py -j 4 -r 2

# 设置超时 2 小时，UVM 高详细度
python3 regr_run.py -t 2 --pl UVM_HIGH

# 启用 URG 覆盖率报告
python3 regr_run.py --urg

# 禁用覆盖率（加快仿真速度）
python3 regr_run.py --no-coverage

# 只查看将执行的编译和仿真命令
python3 regr_run.py --show-commands

# 只编译
python3 regr_run.py --compile-only

# 只仿真（要求已有 simv）
python3 regr_run.py --sim-only -j 4

# 完整示例
python3 regr_run.py -c regress.cfg -l case.lst -j 4 -r 2 -t 2 --pl UVM_HIGH --urg
```

### 日志与实时报告

- 所有过程日志统一输出到终端和结果目录下的 `logging.txt`
- `logging.txt` 采用追加写模式，多次回归会保留历史内容
- 回归运行期间会每 3 分钟打印一次进度摘要：`running / pending / completed / failed / elapsed`
- `report_<timestamp>.html` 会周期性刷新，可实时查看当前进度、正在运行的 case 列表和最终结果

示例日志片段：

```
Step 2: Compilation phase
------------------------------------------------------------
Compiling mode: rtl_sim
  Compile: make -f Makefile compile mode=rtl_sim RESULT_DIR=./regress_results_20260322/rtl_sim SIMV_NAME=simv_rtl_sim cov=1
  Success (24.0s)

Step 3: Simulation phase
------------------------------------------------------------
  Running tc_sanity run1/2
    Command: make -f Makefile sim tc=tc_sanity mode=rtl_sim seed=446925936 pl=UVM_MEDIUM RESULT_DIR=./regress_results_20260322/rtl_sim cov=1
    PASS: tc_sanity run1 [7.2s]
```

## 工作原理

1. **解析配置**：加载配置文件，命令行参数覆盖配置文件
2. **解析用例**：读取测试用例列表，提取模式和参数
3. **编译阶段**：按模式编译仿真镜像，支持增量编译
4. **仿真阶段**：并行执行仿真，支持超时和重试
5. **结果判定**：解析 UVM 报告摘要，判定通过/失败
6. **报告生成**：生成 HTML 报告和覆盖率报告

## 结果目录

运行后自动生成结果目录：

```
./regress_results_YYYYMMDD/
├── rtl_sim/                 # 仿真模式目录
│   ├── case1_12345.log      # 仿真日志
│   ├── case2_67890.log
│   ├── compile_rtl_sim.log  # 编译日志
│   ├── simv_rtl_sim         # 编译镜像
│   └── simv_rtl_sim.vdb     # 覆盖率数据库
├── coverage_report/         # URG 报告（如启用）
├── logging.txt              # 统一追加日志
└── report_<timestamp>.html  # HTML 测试报告（运行中会实时刷新）
```

## Makefile 要求

项目 Makefile 需支持以下目标和变量：

```makefile
# 编译目标
compile:
    vcs $(VCS_ARGS) -lca -o $(SIMV_NAME) ...

# 仿真目标
sim:
    ./$(SIMV_NAME) $(SIM_ARGS) ...

# 支持的变量
# tc          - 测试用例名称
# mode        - 仿真模式
# seed        - 随机种子
# pl          - UVM 打印等级
# RESULT_DIR  - 结果目录
# COV_ARGS    - 覆盖率参数
# cov         - 是否启用覆盖率 (0/1)
```

## 验证状态

**功能验证完成** (2026-04-03)

| 功能 | 状态 | 说明 |
|------|------|------|
| `--show-commands` | ✓ | 正确输出编译/仿真命令 |
| `--compile-only` | ✓ | 编译成功 (23.5s) |
| `--sim-only -j 2` | ✓ | 跳过编译，并行仿真 |
| 完整回归 | ✓ | 全流程正常 |
| 错误处理 | ✓ | 文件不存在/互斥参数检测 |

## 注意事项

1. **执行目录**：脚本必须在包含 `Makefile` 的目录下执行
2. **结果目录**：自动生成为 `./regress_results_YYYYMMDD`
3. **覆盖率**：默认启用，可使用 `--no-coverage` 禁用
4. **结果判定**：基于 UVM 报告摘要中的 FATAL/ERROR 计数
5. **日志模式**：`logging.txt` 采用追加模式，多次运行保留历史

## 依赖

- Python 3.6+
- Synopsys VCS
- UVM 1.2
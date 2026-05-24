# IC 验证回归仿真脚本需求规格说明书

## 1. 脚本目标
开发一个 Python3 回归仿真脚本，用于自动化执行 IC 验证测试用例，支持并行执行、失败重试、结果收集、HTML 报告生成、优雅退出以及多种执行模式。

## 2. 仿真工具与环境
- **仿真器**：Synopsys VCS
- **执行环境**：本地单机运行，利用多核并行
- **环境配置**：脚本假设用户 shell 已配置所有环境变量（工具路径、License 等），脚本直接调用 `make` 命令。

## 3. 外部依赖

### 3.1 测试用例列表文件 (case.lst)
- **文件格式**：文本文件，每行定义一个测试用例
- **编码**：UTF-8
- **行格式**：空格分隔的 `KEY=VALUE` 键值对
- **必填字段**：
  - `tc`：测试用例名称（如 `tc=tc_abc`），必须为有效标识符（以字母或下划线开头，后接字母、数字或下划线）
  - `mode`：仿真模式（如 `mode=rtl_sim`），相同 `mode` 的用例共享编译选项和宏，回归时只需编译一次
- **可选字段**：
  - `times`：重复执行次数（正整数，默认为 1）
  - `seed`：随机种子（非负整数），不指定时脚本自动生成基于时间戳的唯一种子
- **其他字段**：如 `udc`、`udr` 等会作为额外参数传递给仿真命令
- **注释支持**：支持空行和 `#` 开头的注释行
- **示例**：
```
# 基础测试用例
tc=tc_sanity mode=rtl_sim times=2
tc=tc_feature_a mode=rtl_sim udr=+testname=feature_a times=1 seed=12345

# 回归测试用例
tc=tc_regression mode=gate_sim times=3
```

### 3.2 Makefile
脚本依赖项目目录下的 Makefile，Makefile 必须支持以下目标和变量：

#### 3.2.1 必需的 Make 目标
- **compile**：编译目标，生成仿真可执行文件
- **sim**：仿真目标，执行单个测试用例

#### 3.2.2 必需的 Make 变量
| 变量名 | 说明 | 示例值 |
|--------|------|--------|
| `tc` | 测试用例名称 | `tc_sanity` |
| `mode` | 仿真模式，用于编译产物命名 | `rtl_sim` |
| `seed` | 随机种子 | `12345` |
| `pl` | UVM 打印级别 | `UVM_MEDIUM` |
| `RESULT_DIR` | 输出目录 | `./regress_results_20260322/rtl_sim` |
| `SIMV_NAME` | 编译产物名称（仅编译时使用） | `simv_rtl_sim` |
| `cov` | 覆盖率开关（0 或 1） | `1` |
| `COV_ARGS` | 覆盖率参数（可选） | `-cm line+cond+branch+fsm` |

#### 3.2.3 Makefile 示例结构
```makefile
# 基本变量
tc ?=
mode ?=
seed ?= 1
pl ?= UVM_MEDIUM
RESULT_DIR ?= out
SIMV_NAME ?= simv
cov ?= 1
COV_ARGS ?= -cm line+cond+branch+fsm+tgl+assert

# 编译目标
compile:
	vcs $(VCS_OPTS) $(COV_ARGS) -o $(RESULT_DIR)/$(SIMV_NAME) ...

# 仿真目标
sim:
	./$(RESULT_DIR)/simv_$(mode) +UVM_VERBOSITY=$(pl) -smlowmem ...

# 清理目标
clean:
	rm -rf $(RESULT_DIR)
```

### 3.2.4 可选的辅助文件
以下文件如果存在于当前目录，会被自动复制到仿真结果目录：
- **run.tcl**：仿真运行脚本
- **cm.cfg**：覆盖率配置文件

### 3.3 配置文件 (regress.cfg)
- **文件格式**：INI 格式，`KEY = VALUE` 形式
- **编码**：UTF-8
- **注释支持**：支持 `#` 开头的注释行
- **优先级**：命令行参数 > 配置文件 > 默认值

## 4. 测试用例管理

### 4.1 测试用例解析
- 解析 case.lst 文件，提取所有测试用例
- 验证必填字段（tc、mode）是否存在
- 验证字段格式是否合法（标识符格式、数值范围等）
- 统计各 mode 的唯一值，确定编译次数

### 4.2 测试用例验证
- 测试用例名称必须为有效标识符
- mode 名称必须为有效标识符
- times 必须 ≥ 1
- seed 如果指定，必须 ≥ 0

### 4.3 测试用例执行顺序
- 按照 case.lst 中的顺序提交任务
- 同一测试用例的多次重复（times > 1）串行执行
- 不同测试用例可以并行执行

## 5. 仿真命令构建

### 5.1 编译命令
```bash
make -f Makefile compile mode=<mode> RESULT_DIR=<result_dir>/<mode> SIMV_NAME=simv_<mode> cov=<0|1> [COV_ARGS=...] [global_args...]
```

### 5.2 仿真命令
```bash
make -f Makefile sim tc=<tc> mode=<mode> seed=<seed> pl=<UVM_level> RESULT_DIR=<result_dir>/<mode> cov=<0|1> [extra_args...] [global_args...]
```

### 5.3 参数传递顺序
全局参数 → 覆盖率参数 → 测试用例特定参数（后传入的参数会覆盖同名参数）

## 6. 执行模式

### 6.1 正常模式（默认）
- 执行完整流程：解析 → 编译 → 仿真 → 生成报告

### 6.2 干跑模式（--dry-run 或 --show-commands）
- 只打印命令，不实际执行
- 用于验证命令构建是否正确

### 6.3 仅编译模式（--compile-only）
- 只执行编译阶段，不运行仿真
- 用于提前发现编译错误

### 6.4 跳过编译模式（--skip-compile 或 --sim-only）
- 跳过编译阶段，直接运行仿真
- 要求 simv 已存在，否则报错

## 7. 并行执行策略

### 7.1 并发控制
- 通过 `-j <N>` 或 `--jobs <N>` 指定并行任务数
- 默认值为 1（串行执行）
- 使用线程池管理并行任务

### 7.2 执行策略
- 每个测试用例作为独立任务提交到线程池
- 同一测试用例的多次重复串行执行
- 失败的任务不影响其他任务执行

### 7.3 超时控制
- 每个仿真运行有超时限制（默认 1 小时）
- 通过 `--timeout` 或配置文件 `timeout` 设置（单位：小时）
- 超时后自动终止仿真进程

## 8. 结果判定

### 8.1 综合判定规则
一次仿真执行被认为**通过**，需同时满足：
1. **退出码**：仿真进程返回退出码 0
2. **日志关键字**：仿真日志不匹配失败关键字模式

否则，执行结果为**失败**。

### 8.2 默认失败关键字
默认正则表达式匹配 UVM Report Summary 中的计数（非单行日志）：
```
UVM_FATAL\s*:\s*[1-9]\d*|UVM_ERROR\s*:\s*[1-9]\d*
```

**说明**：此模式匹配：
- `UVM_FATAL : 1` 到 `UVM_FATAL : 99...`（非零计数）
- `UVM_ERROR : 1` 到 `UVM_ERROR : 99...`（非零计数）

**避免误报**：
- 日志消息体中包含 `UVM_ERROR` 不会触发
- `UVM_ERROR : 0` 等零计数行不会触发

### 8.3 自定义关键字
用户可通过命令行参数配置：
```bash
--fail-keywords "UVM_FATAL|UVM_ERROR|TIMEOUT"
--pass-keywords "TEST PASSED|SIMULATION SUCCESS"
```

判定逻辑：先检查失败关键字，如无匹配再检查成功关键字。

### 8.4 UVM Summary 提取
脚本自动从仿真日志中提取 UVM Report Summary 信息，包括：
- UVM_FATAL 计数
- UVM_ERROR 计数
- UVM_WARNING 计数

## 9. 失败重试机制

### 9.1 重试次数
通过 `--retry N` 或 `-r N` 指定（N ≥ 0，默认为 0）

### 9.2 重试策略
- 单次仿真执行失败时，自动重试最多 N 次
- 任一次重试成功，则标记为成功，停止重试
- 所有重试均失败，则标记为最终失败
- 重试时使用**相同的种子**以保证可复现性

### 9.3 重试范围
仅针对失败的单次执行实例，不影响同一测试用例的其他重复执行。

### 9.4 用例级成功判定
当 `times > 1` 时，采用**严格模式**：
- 测试用例通过条件：**所有**执行实例均通过
- 示例：`times=3`，Run1=Pass, Run2=Pass, Run3=Fail → 用例结果 = **FAIL**

### 9.5 重试历史记录
报告中显示：
- 首次尝试状态
- 重试次数（如有）
- 最终状态
- 示例显示：`PASS (after 2 retries)` 或 `FAIL (3/3 retries failed)`

## 10. 日志与结果存储

### 10.1 根目录
通过 `--result-dir` 或配置文件指定，默认自动生成为 `./regress_results_YYYYMMDD`

### 10.2 目录结构
```
<regress_results_YYYYMMDD>/
├── logging.txt                    # 回归全程日志（追加模式）
├── <mode>/                        # 仿真模式目录（如 rtl_sim）
│   ├── simv_<mode>                # 编译产物
│   ├── simv_<mode>.daidir/        # VCS 设计数据目录
│   ├── simv_<mode>.vdb/           # 覆盖率数据库
│   ├── compile_<mode>.log         # 编译日志
│   ├── <case>_<seed>.log          # 仿真日志文件
│   ├── sim_<case>_<seed>.fsdb     # 波形文件
│   ├── run.tcl                    # 仿真运行脚本（从当前目录复制）
│   └── cm.cfg                     # 覆盖率配置（从当前目录复制）
├── coverage_report/               # URG 覆盖率报告（启用 --urg 时）
└── report_<timestamp>.html        # HTML 测试报告
```

### 10.3 文件命名规则
- **仿真日志**：`<case>_<seed>.log`（如 `tc_sanity_1499049797.log`）
- **波形文件**：`sim_<case>_<seed>.fsdb`（如 `sim_tc_sanity_1499049797.fsdb`）
- **编译日志**：`compile_<mode>.log`
- **HTML 报告**：`report_<timestamp>.html`

### 10.4 清理策略
不自动清理中间文件，由用户自行管理。

## 11. 报告生成

### 11.1 报告格式
HTML 格式，支持自动刷新（每 30 秒）

### 11.2 报告内容

#### 11.2.1 运行状态区域
- 当前状态（运行中/已停止）
- 已运行时间
- 最后更新时间
- 统计卡片：总数、已完成、运行中、等待中、失败数
- 运行中用例表格：测试用例、模式、种子、开始时间、已运行时间、命令

#### 11.2.2 摘要区域
- 统计卡片：
  - 总用例数、通过/失败数
  - 用例通过率
  - 总运行次数、通过/失败次数
  - 运行通过率
  - 总耗时

#### 11.2.3 测试用例详情区域
- 每个用例显示：名称、模式、运行次数统计、通过/失败状态
- 支持展开/折叠查看详细运行结果
- 每次运行显示：运行编号、种子、状态（含重试次数）、耗时、日志链接、错误信息

### 11.3 报告位置
与结果目录同级，文件名包含时间戳（如 `report_20250322_143015.html`）

### 11.4 动态更新
- 回归执行期间每 30 秒更新一次 HTML 报告
- 显示实时运行的测试用例和进度

## 12. 覆盖率收集

### 12.1 开关控制
- **默认状态**：默认开启覆盖率收集
- **禁用方式**：使用 `--no-coverage` 参数
- **启用方式**：使用 `--coverage` 参数显式启用

### 12.2 覆盖率参数
通过 `--coverage-args` 指定覆盖率类型：
```bash
--coverage-args "-cm line+cond+branch+fsm"
```

### 12.3 默认覆盖率类型
如果启用覆盖率但未指定 `--coverage-args`，默认为：
```
-cm line+cond+branch+fsm+tgl+assert
```

### 12.4 参数传递
覆盖率通过 `cov=<0|1>` 标志传递给 Makefile：
```bash
make sim tc=<case> mode=<mode> cov=1
```

### 12.5 覆盖率数据处理
- **编译阶段**：覆盖率选项包含在 simv 编译中
- **仿真阶段**：每次仿真运行将覆盖率数据追加到 `simv_<mode>.vdb`
- **URG 报告**：仿真完成后可通过 `--urg` 参数生成 URG 合并报告，输出到 `<result_dir>/coverage_report/`

## 13. 版本控制集成
- **功能**：记录回归开始时的 Git 版本（commit hash），显示在报告中
- **实现**：自动执行 `git rev-parse HEAD` 获取版本号
- **异常处理**：不在 Git 仓库中时标记为 'N/A'

## 14. 配置方式

### 14.1 配置优先级
命令行参数 > 配置文件 > 脚本默认值

### 14.2 配置文件格式
- 基本格式：`KEY = VALUE`，每行一个参数
- 支持 `#` 开头的注释行
- 支持参数别名（兼容不同命名习惯）

### 14.3 参数别名映射
| 配置文件参数名 | 命令行参数 | 说明 |
|---------------|-----------|------|
| `jobs` | `-j, --jobs` | 并行任务数 |
| `retry` | `-r, --retry` | 失败重试次数 |
| `timeout` / `time_out` | `--timeout` | 单次仿真超时（小时） |
| `case_list` / `caselist` | `-l, --case-list` | 测试用例列表文件 |
| `pl` | `--pl` | UVM 打印级别 |
| `coverage` | `--coverage/--no-coverage` | 覆盖率开关 |
| `coverage_args` | `--coverage-args` | 覆盖率参数 |
| `urg_report` / `urg` | `--urg` | URG 报告生成 |
| `fail_keywords` / `log_keywords` | `--fail-keywords` | 失败关键字正则 |
| `pass_keywords` | `--pass-keywords` | 成功关键字正则 |
| `global_args` | `-g, --global-args` | 全局 make 参数 |

### 14.4 配置文件示例 (regress.cfg)
```ini
# 回归仿真配置文件

# 并行任务数
jobs = 8

# 失败重试次数
retry = 1

# 单次仿真超时（小时）
timeout = 1

# 测试用例列表文件
case_list = case.lst

# UVM 打印级别 (UVM_LOW, UVM_MEDIUM, UVM_HIGH, UVM_FULL, UVM_DEBUG)
pl = UVM_MEDIUM

# 启用覆盖率收集
coverage = true

# 覆盖率参数
coverage_args = -cm line+cond+branch+fsm

# 生成 URG 报告
urg_report = true

# 失败关键字正则表达式
fail_keywords = UVM_FATAL\s*:\s*[1-9]\d*|UVM_ERROR\s*:\s*[1-9]\d*

# 全局 make 参数
global_args = USE_VCS=1 VERBOSITY=UVM_HIGH
```

## 15. 日志输出

### 15.1 日志文件
- 所有回归输出记录到 `<result_dir>/logging.txt`
- 使用追加模式，保留完整执行记录

### 15.2 命令输出
默认输出所有 make 命令：
- **编译阶段**：输出完整 `make compile` 命令
- **仿真阶段**：输出每个运行的完整 `make sim` 命令
- **格式**：显示命令行、执行结果、耗时

### 15.3 输出示例
```
============================================================
IC Verification Regression Simulation
Regression started at: 2026-03-22 14:30:15
Work directory: /home/user/project
Git commit: abc123def456
Case list: case.lst
------------------------------------------------------------
Regression Configuration:
  Case list:    case.lst
  Result dir:   ./regress_results_20260322
  Jobs:         4
  Retry:        1
  Timeout:      1h (3600s)
  Coverage:     True
------------------------------------------------------------
Step 1: Parsing test case list
------------------------------------------------------------
Found 10 test cases
Modes: rtl_sim
Total simulation runs: 15

Step 2: Compilation phase
------------------------------------------------------------
Compiling mode: rtl_sim
Compile: make -f Makefile compile mode=rtl_sim RESULT_DIR=./regress_results_20260322/rtl_sim SIMV_NAME=simv_rtl_sim cov=1
Compilation success for rtl_sim (24.0s)

Step 3: Simulation phase
------------------------------------------------------------
Starting regression with 10 cases, 15 total runs, 4 parallel jobs
Running tc_sanity run1/2
  Command: make -f Makefile sim tc=tc_sanity mode=rtl_sim seed=446925936 pl=UVM_MEDIUM RESULT_DIR=./regress_results_20260322/rtl_sim cov=1
  PASS: tc_sanity run1 [7.2s]

[Progress] total=15 completed=5 running=4 pending=6 failed=0 elapsed=00:02:30

Step 5: Generating HTML report
------------------------------------------------------------
Report generated: ./regress_results_20260322/report_20260322_143015.html

Summary
------------------------------------------------------------
Regression completed at: 2026-03-22 14:45:30
Total duration: 15m 15s
Cases: 9/10 passed (90.0%)
Runs: 13/15 passed (86.7%)
Failed cases:
  - tc_feature_b: 1/3 runs failed
Report: ./regress_results_20260322/report_20260322_143015.html

REGRESSION FAILED
```

### 15.4 调试模式
使用 `-d` 或 `--debug` 启用调试信息：
- HTML 报告更新错误
- 其他内部调试消息

### 15.5 进度报告
- 每 3 分钟输出一次进度信息
- 显示：总数、已完成、运行中、等待中、失败数、已运行时间

## 16. 信号处理与优雅退出

### 16.1 支持的信号
- **SIGINT**（Ctrl+C）：优雅退出
- **SIGTERM**：优雅退出

### 16.2 退出行为
- **首次中断**：停止所有运行中的仿真，生成最终报告，退出码 130
- **再次中断**：强制退出，退出码 130

### 16.3 清理操作
退出时执行：
- 终止所有运行中的仿真进程
- 停止状态跟踪器
- 生成包含部分结果的 HTML 报告

## 17. 异常处理与退出码

### 17.1 错误处理
- 配置错误（用例列表文件不存在、参数无效等）：打印错误信息，退出码 1
- 编译失败：打印失败模式，退出码 1
- 单个测试用例异常：记录错误，不影响其他用例执行

### 17.2 退出码定义
| 退出码 | 含义 |
|--------|------|
| 0 | 所有测试用例通过 |
| 1 | 至少一个测试用例失败，或配置错误 |
| 130 | 用户中断（SIGINT/SIGTERM） |

### 17.3 最终摘要
回归完成后输出：
- 总耗时
- 用例级统计：通过/总用例数、通过率
- 运行级统计：通过/总运行次数、通过率
- 失败用例列表（含失败次数）
- 报告文件路径

## 18. UVM 打印级别
- **参数**：`--pl` 或配置文件 `pl`
- **有效值**：UVM_LOW、UVM_MEDIUM、UVM_HIGH、UVM_FULL、UVM_DEBUG
- **默认值**：UVM_MEDIUM
- **传递方式**：作为 `pl=<level>` 传递给 Makefile

## 19. 可扩展性考虑
- 未来可能需要支持其他仿真器（如 Xcelium、Questa）或集群调度系统，脚本应保持仿真命令构建部分的可配置性
- 结果判定规则可能需要扩展（如检查特定文件是否存在），建议将判定逻辑抽象为可配置函数或插件

## 20. 非功能性需求
- **性能**：并行执行时控制并发数，避免系统过载
- **健壮性**：单个测试用例的异常不应导致整个回归终止
- **可维护性**：模块化代码结构，职责清晰分离
- **实时可见性**：HTML 报告提供实时状态更新和自动刷新

---

## 改进意见

### 1. 功能增强建议

#### 1.1 配置文件支持 Makefile 路径配置
当前实现中 Makefile 路径固定为当前目录下的 `Makefile`，建议支持通过配置文件或命令行参数指定 Makefile 路径，增强灵活性：
```ini
makefile = ../rsim/Makefile
```

#### 1.2 种子生成策略优化
当前种子生成基于时间戳和哈希值，建议增加以下选项：
- 支持固定种子模式（所有测试用例使用相同种子基础值）
- 支持种子范围配置（如 `seed_range=1000-9999`）
- 记录种子生成日志便于复现

#### 1.3 失败用例自动重跑
建议增加失败用例自动重跑功能：
- 生成失败用例列表文件 `failed_cases.lst`
- 支持通过 `--rerun-failed` 参数直接重跑失败的用例

#### 1.4 进度报告增强
当前进度报告每 3 分钟输出一次，建议增加：
- 支持自定义进度报告间隔
- 进度百分比显示
- 预估剩余时间

#### 1.5 结果目录命名增强
当前结果目录仅包含日期，建议增加更多选项：
- 支持自定义前缀/后缀
- 支持包含 Git 分支名或 commit hash
- 支持时间戳精确到秒

### 2. 报告功能改进

#### 2.1 历史报告对比
建议增加与历史回归报告的对比功能：
- 显示通过率变化趋势
- 标记新增失败用例
- 标记已修复用例

#### 2.2 详细错误信息展示
建议在 HTML 报告中增强错误信息展示：
- UVM Summary 详细信息（UVM_FATAL、UVM_ERROR、UVM_WARNING 计数）
- 错误日志片段预览
- 波形文件链接（如果有 fsdb 文件）

#### 2.3 覆盖率集成展示
建议在 HTML 报告中集成覆盖率信息：
- 显示各 mode 的覆盖率数据
- 覆盖率趋势图表
- URG 报告链接

#### 2.4 报告导出功能
建议增加报告导出功能：
- 支持导出 PDF 格式
- 支持导出 JSON/XML 数据格式
- 支持邮件发送报告摘要

### 3. 执行效率优化

#### 3.1 编译缓存策略优化
当前默认强制重新编译，建议优化：
- 支持智能缓存检查（基于源文件修改时间）
- 支持基于 Git commit hash 的缓存管理
- 提供 `--force-compile` 参数用于强制重编译

#### 3.2 并行调度优化
建议优化并行调度策略：
- 支持测试用例优先级配置（优先级高的先执行）
- 支持资源限制（如内存限制）
- 长时间运行用例优先调度（减少总等待时间）

#### 3.3 结果检查优化
建议增加增量结果检查：
- 支持在仿真运行过程中实时检查日志
- 发现失败立即通知，不必等待仿真结束

#### 3.4 增量回归支持
建议支持增量回归：
- 记录已完成的用例和结果
- 支持从中断位置继续执行
- 避免重复执行已通过的用例

### 4. 可维护性改进

#### 4.1 配置文件格式标准化
建议采用更标准的配置文件格式：
- 支持 YAML 或 JSON 格式
- 支持配置文件继承（基础配置 + 项目配置）
- 支持环境变量替换

#### 4.2 日志分级输出
建议增加日志分级：
- 支持不同日志级别（INFO、WARNING、ERROR、DEBUG）
- 分离仿真日志和脚本日志
- 支持日志文件归档

#### 4.3 状态文件持久化
建议增加状态持久化：
- 支持从上次中断位置恢复执行
- 记录执行状态到独立文件
- 支持检查点机制

#### 4.4 模块接口文档化
建议为各模块编写详细接口文档：
- 配置管理模块接口说明
- 测试用例解析模块接口说明
- 执行器模块接口说明
- 报告生成模块接口说明

### 5. 用户体验改进

#### 5.1 命令行帮助完善
建议完善命令行帮助信息：
- 增加参数示例说明
- 支持参数分组显示
- 增加常见使用场景示例

#### 5.2 错误信息友好化
建议改进错误信息提示：
- 提供更具体的错误原因说明
- 提供可能的解决方案建议
- 支持错误码标准化

#### 5.3 输出格式美化
建议美化终端输出：
- 支持颜色输出（PASS 绿色、FAIL 红色）
- 支持表格格式输出统计信息
- 支持进度条显示

#### 5.4 交互模式支持
建议增加交互模式：
- 支持在运行过程中动态调整并发数
- 支持在运行过程中跳过/重跑特定用例
- 支持实时查看特定用例日志

### 6. 兼容性扩展

#### 6.1 其他仿真器支持
建议预留其他仿真器支持接口：
- 支持 Xcelium 仿真器
- 支持 Questa 仿真器
- 支持 Verilator 仿真器

#### 6.2 分布式执行支持
建议预留分布式执行能力：
- 支持 LSF/SGE 集群调度
- 支持远程执行节点
- 支持任务分发和结果收集

#### 6.3 操作系统兼容性
建议增强操作系统兼容性：
- 明确支持 Linux 发行版列表
- 测试与不同 Python 版本的兼容性
- 处理不同 shell 环境的差异

### 7. 文档完善建议

#### 7.1 用户手册
建议编写完整的用户手册：
- 快速入门指南
- 配置文件详细说明
- 常见问题解答
- 最佳实践建议

#### 7.2 示例模板
建议提供示例模板：
- 标准配置文件模板
- 标准测试用例列表模板
- 标准 Makefile 模板
- 项目集成示例

#### 7.3 故障排除指南
建议编写故障排除指南：
- 常见错误及解决方法
- 日志分析指南
- 性能调优建议

### 8. 安全性考虑

#### 8.1 输入验证
建议增强输入验证：
- 验证文件路径安全性
- 验证参数值范围
- 防止命令注入

#### 8.2 资源保护
建议增加资源保护机制：
- 磁盘空间检查
- 内存使用监控
- 进程数量限制

#### 8.3 错误恢复
建议增强错误恢复能力：
- 异常情况下的数据保护
- 部分失败后的继续执行
- 关键操作的确认机制
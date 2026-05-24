# IC 验证回归脚本代码解读指南

> 本文档面向 Python 初学者，帮助你理解回归仿真脚本的设计与实现。

---

## 一、项目概述

### 1.1 脚本功能

这是一个 **IC 验证回归仿真脚本**，用于自动化执行芯片验证测试用例。主要功能包括：

- **并行执行**：多个测试用例同时运行，提高效率
- **失败重试**：测试失败后自动重试，避免偶发错误
- **结果判定**：自动检查日志中的错误/成功关键字
- **报告生成**：生成 HTML 格式的测试报告
- **覆盖率收集**：支持 VCS 代码覆盖率统计

### 1.2 执行流程概览

```
┌─────────────────────────────────────────────────────────────┐
│                    回归仿真执行流程                                 │
├─────────────────────────────────────────────────────────────┤
│  1. 解析命令行参数和配置文件                                             │
│     ↓                                                       │
│  2. 解析测试用例列表 (case.lst)                                           │
│     ↓                                                       │
│  3. 编译仿真镜像 (每个 mode 生成一个 simv)                                    │
│     ↓                                                       │
│  4. 并行执行仿真                                                   │
│     ↓                                                       │
│  5. 检查结果、重试失败用例                                              │
│     ↓                                                       │
│  6. 生成 HTML 报告                                                 │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、目录结构

```
/home/IC_verify/script/regression/
├── regr_run.py             # 主入口脚本
├── case.lst              # 测试用例列表
├── regress.cfg             # 配置文件
├── Makefile              # 编译和仿真 Makefile
└── regr/                # 核心模块目录
    ├── __init__.py         # Python 包初始化文件
    ├── config.py          # 配置管理模块
    ├── case_parser.py       # 用例解析模块
    ├── compiler.py         # 编译管理模块
    ├── executor.py         # 并行执行模块 (核心)
    ├── result_checker.py      # 结果判定模块
    ├── reporter.py         # 报告生成模块
    ├── status_tracker.py      # 状态跟踪模块
    └── utils.py          # 工具函数模块
```

---

## 三、Python 基础知识

在阅读代码前，需要了解以下 Python 概念：

### 3.1 dataclass 数据类

Python 3.7+ 引入的装饰器，用于自动生成类的 `__init__`、`__repr__` 等方法。

```python
from dataclasses import dataclass

# 传统写法
class TestCase:
    def __init__(self, tc, mode, times=1):
        self.tc = tc
        self.mode = mode
        self.times = times

# dataclass 写法 (更简洁)
@dataclass
class TestCase:
    tc: str           # 测试用例名
    mode: str         # 仿真模式
    times: int = 1    # 重复次数，默认值 1
```

**好处**：
- 自动生成构造函数
- 自动生成字符串表示
- 支持类型注解

### 3.2 类型注解 (Type Hints)

Python 3.5+ 支持的类型提示，让代码更易读。

```python
from typing import List, Optional, Dict

def parse(self, filepath: str) -> List[TestCase]:
    """
    参数类型: str
    返回类型: List[TestCase] (TestCase 对象的列表)
    """
    pass

# Optional 表示可选，可以是 int 或 None
seed: Optional[int] = None

# Dict 表示字典类型
extra_args: Dict[str, str] = {}
```

### 3.3 模块导入

```python
# 导入整个模块
import os

# 导入模块中的特定对象
from pathlib import Path

# 从相对路径导入 (用于包内部)
from .config import RegressionConfig  # . 表示当前目录
```

### 3.4 列表推导式

简洁地创建列表的方式。

```python
# 传统写法
passed_cases = []
for r in results:
    if r.passed:
        passed_cases.append(r)

# 列表推导式写法
passed_cases = [r for r in results if r.passed]

# 更多示例
numbers = [1, 2, 3, 4, 5]
doubled = [n * 2 for n in numbers]  # [2, 4, 6, 8, 10]
```

### 3.5 with 上下文管理器

自动管理资源，确保文件正确关闭。

```python
# 传统写法
f = open('file.txt', 'r')
try:
    content = f.read()
finally:
    f.close()

# with 写法 (推荐)
with open('file.txt', 'r') as f:
    content = f.read()
# 文件自动关闭，即使发生异常
```

---

## 四、执行流程详解

### 4.1 主入口 (regr_run.py)

```python
def main():
    """主入口函数"""
    runner = RegressionRunner()
    return runner.run()
```

执行流程：

1. **信号处理**：捕获 Ctrl+C 信号，优雅退出
2. **参数解析**：读取命令行参数和配置文件
3. **用例解析**：读取 case.lst 文件
4. **编译阶段**：为每个 mode 编译 simv
5. **仿真阶段**：并行执行所有测试用例
6. **报告生成**：输出 HTML 报告

### 4.2 配置优先级

```
命令行参数 > 配置文件 > 默认值
```

示例：
```bash
# 配置文件设置 jobs=4
# 命令行指定 -j 8
# 最终使用 jobs=8 (命令行优先级最高)
python regr_run.py -j 8
```

---

## 五、核心模块解读

### 5.1 配置模块 (config.py)

**职责**：管理回归仿真的所有配置参数

#### 核心数据类

```python
@dataclass
class RegressionConfig:
    # 路径配置
    case_list: str = "case.lst"   # 用例列表文件
    target: str = "sim"       # Makefile 目标

    # 执行配置
    jobs: int = 1          # 并行任务数
    retry: int = 0          # 失败重试次数
    timeout: int = 1         # 超时时间 (小时)

    # 覆盖率配置
    coverage: bool = True      # 是否收集覆盖率

    # 结果判定
    fail_keywords: str = ""       # 失败关键字正则
    pass_keywords: str = ""       # 成功关键字正则
```

#### `__post_init__` 方法

dataclass 对象创建后自动调用的方法：

```python
def __post_init__(self):
    # 小时转秒
    self.timeout_seconds = self.timeout * 3600

    # 自动生成结果目录名
    from datetime import datetime
    date_str = datetime.now().strftime('%Y%m%d')
    self.result_dir = f"./regress_results_{date_str}"
```

#### 配置加载流程

```python
@classmethod
def load(cls, args) -> "RegressionConfig":
    config = cls()  # 使用默认值创建

    # 1. 从配置文件加载
    config._load_from_file(config_file)

    # 2. 命令行参数覆盖
    config._override_from_args(args)

    return config
```

### 5.2 用例解析模块 (case_parser.py)

**职责**：解析 case.lst 文件，提取测试用例信息

#### 用例列表文件格式

```
# 注释行
tc=tc_sanity mode=rtl_sim times=2
tc=tc_burst mode=rtl_sim seed=12345
```

#### TestCase 数据类

```python
@dataclass
class TestCase:
    tc: str                      # 用例名 (必须)
    mode: str                    # 仿真模式 (必须)
    times: int = 1               # 重复次数
    seed: Optional[int] = None   # 随机种子
    extra_args: Dict = {}        # 额外参数
    line_num: int = 0            # 行号 (用于错误定位)
```

#### 解析流程

```python
def parse(self, filepath: str) -> List[TestCase]:
    with open(filepath, 'r') as f:
        for line_num, line in enumerate(f, 1):  # enumerate 从1开始计数
            line = line.strip()

            # 跳过空行和注释
            if not line or line.startswith('#'):
                continue

            # 解析 KEY=VALUE 对
            case, error = self._parse_line(line, line_num)
            if case:
                self.cases.append(case)

    return self.cases
```

#### 字符串分割技巧

```python
# split() 无参数：按空白字符分割
line = "tc=tc_sanity  mode=rtl_sim\ttimes=2"
parts = line.split()  # ['tc=tc_sanity', 'mode=rtl_sim', 'times=2']

# split('=', 1)：只分割第一个等号
part = "udr=+a=1+b=2"
key, value = part.split('=', 1)  # key='udr', value='+a=1+b=2'
```

### 5.3 编译模块 (compiler.py)

**职责**：管理 VCS 编译过程，生成仿真镜像

#### CompileResult 数据类

```python
@dataclass
class CompileResult:
    mode: str         # 编译模式
    success: bool       # 是否成功
    log_path: str       # 编译日志路径
    simv_path: str       # 生成的 simv 路径
    duration: float      # 编译耗时
    error_message: str     # 错误信息
```

#### 编译命令构建

```python
def build_compile_command(self, mode: str) -> List[str]:
    cmd = ['make', '-f', 'Makefile', 'compile']
    cmd.append(f'mode={mode}')
    cmd.append(f'RESULT_DIR={result_dir}')
    cmd.append(f'SIMV_NAME=simv_{mode}')

    if self.config.coverage:
        cmd.append(f'COV_ARGS={self.config.coverage_args}')
        cmd.append('cov=1')

    return cmd
```

#### 执行编译

```python
def compile_mode(self, mode: str) -> CompileResult:
    cmd = self._build_compile_command(mode)

    # 使用 subprocess 执行命令
    with open(log_path, 'w') as log_file:
        result = subprocess.run(
            cmd,
            stdout=log_file,       # 输出重定向到文件
            stderr=subprocess.STDOUT,  # 错误也输出到文件
            timeout=timeout
        )

    if result.returncode == 0:
        return CompileResult(success=True, ...)
    else:
        return CompileResult(success=False, ...)
```

### 5.4 执行模块 (executor.py) - 核心

**职责**：并行执行仿真，管理重试和超时

这是脚本最复杂的模块，涉及多线程编程。

#### RunResult 数据类

```python
@dataclass
class RunResult:
    tc: str           # 用例名
    mode: str         # 仿真模式
    run_id: int       # 运行序号
    seed: int         # 随机种子
    passed: bool      # 是否通过
    log_path: str     # 日志路径
    duration: float   # 耗时
```

#### CaseResult 数据类

```python
@dataclass
class CaseResult:
    tc: str
    mode: str
    times: int
    runs: List[RunResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """属性：所有运行都通过才算通过"""
        return all(run.passed for run in self.runs)

    @property
    def pass_count(self) -> int:
        """属性：通过的运行数"""
        return sum(1 for run in self.runs if run.passed)
```

#### 多线程执行

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def run_all(self, cases: List[TestCase]) -> Dict[str, CaseResult]:
    results = {}

    # 创建线程池
    with ThreadPoolExecutor(max_workers=self.config.jobs) as executor:
        # 提交所有任务
        futures = {
            executor.submit(self._execute_case, case): case
            for case in cases
        }

        # 收集结果
        for future in as_completed(futures):
            case = futures[future]
            case_result = future.result()
            results[case.tc] = case_result

    return results
```

**关键概念**：
- `ThreadPoolExecutor`：线程池，管理多个工作线程
- `executor.submit()`：提交任务到线程池
- `as_completed()`：按完成顺序迭代 Future 对象
- `future.result()`：获取任务返回值

#### 线程安全

多线程环境下，共享数据需要加锁：

```python
import threading

self._lock = threading.Lock()
self._completed_count = 0

def update_progress():
    with self._lock:  # 加锁
        self._completed_count += 1
    # 自动解锁
```

#### 超时处理

```python
process = subprocess.Popen(cmd, ...)

try:
    # 等待进程结束，设置超时
    exit_code = process.wait(timeout=self.config.timeout_seconds)
except subprocess.TimeoutExpired:
    # 超时后杀死进程
    process.kill()
    process.wait()
    raise
```

#### 优雅停止

```python
import threading

self._stop_event = threading.Event()

def stop(self):
    """设置停止标志"""
    self._stop_event.set()

def _run_single(self, case, run_id):
    """检查是否需要停止"""
    if self._stop_event.is_set():
        return RunResult(passed=False, error_message="Stopped")
    # 继续执行...
```

### 5.5 结果判定模块 (result_checker.py)

**职责**：检查仿真日志，判定通过/失败

#### 判定逻辑

```python
def check(self, log_path: str, exit_code: int) -> CheckResult:
    # 1. 检查退出码
    if exit_code != 0:
        return CheckResult(passed=False, error="Non-zero exit code")

    # 2. 读取日志
    with open(log_path, 'r') as f:
        log_content = f.read()

    # 3. 检查失败关键字
    if self.fail_pattern:
        matches = self.fail_pattern.findall(log_content)
        if matches:
            return CheckResult(passed=False, error=f"Keywords matched: {matches}")

    # 4. 检查成功关键字
    if self.pass_pattern:
        matches = self.pass_pattern.findall(log_content)
        if matches:
            return CheckResult(passed=True)
        return CheckResult(passed=False, error="Success keywords not found")

    # 5. 默认通过
    return CheckResult(passed=True)
```

#### 正则表达式

```python
import re

# 编译正则表达式 (提高性能)
pattern = re.compile(r'UVM_ERROR\s*:\s*[1-9]\d*', re.IGNORECASE)

# 搜索匹配
matches = pattern.findall(log_content)
# r'UVM_ERROR\s*:\s*[1-9]\d*' 含义：
# UVM_ERROR   - 字面匹配
# \s*         - 0个或多个空白字符
# :           - 字面匹配
# [1-9]\d*    - 非零数字开头，后跟任意数字 (匹配非零计数)
```

### 5.6 状态跟踪模块 (status_tracker.py)

**职责**：实时跟踪运行中的仿真状态，为 HTML 报告提供运行态数据

#### CaseStatus 数据类

```python
@dataclass
class CaseStatus:
    tc: str              # 用例名
    mode: str            # 仿真模式
    seed: int            # 随机种子
    cmd: List[str]       # 执行命令
    start_time: float    # 开始时间戳
    status: str = 'running'  # 状态
```

#### 状态跟踪流程

```python
class StatusTracker:
    def __init__(self):
        self._lock = threading.Lock()       # 线程锁
        self._running_cases: Dict = {}      # 正在运行的用例
        self._completed_count = 0           # 完成计数
        self._failed_count = 0              # 失败计数
        self._total_count = 0               # 总数

    def start_case(self, tc, mode, seed, cmd) -> str:
        """记录用例开始，返回 case_key"""
        case_key = f"{tc}_{mode}_{seed}"
        with self._lock:
            self._running_cases[case_key] = CaseStatus(...)
        return case_key

    def end_case(self, case_key, success):
        """记录用例结束"""
        with self._lock:
            del self._running_cases[case_key]
            if success:
                self._completed_count += 1
            else:
                self._failed_count += 1
```

#### 运行态快照

```python
def get_snapshot(self) -> Dict:
    """获取完整运行态数据，供 HTML 报告使用"""
    return {
        'stats': self.get_statistics(),        # 统计数据
        'running_cases': self.get_running_cases(),  # 正在运行的用例
        'elapsed': self.get_elapsed_time(),    # 已运行时间
        'last_updated': datetime.now(),        # 更新时间
        'stopped': self.is_stopped(),          # 是否已停止
    }
```

#### 与 Executor 集成

```python
# executor.py 中
if self.status_tracker:
    case_key = self.status_tracker.start_case(case.tc, case.mode, seed, cmd)
    # ... 执行仿真 ...
    self.status_tracker.end_case(case_key, passed)
```

#### 与 Reporter 集成

```python
# reporter.py 中
def update_runtime_snapshot(self, snapshot):
    """更新运行态数据，用于实时 HTML 刷新"""
    self.runtime_snapshot = snapshot

def _build_runtime_section(self):
    """构建 HTML 运行态部分"""
    snapshot = self.runtime_snapshot or {}
    stats = snapshot.get('stats', {})
    running_cases = snapshot.get('running_cases', [])
    # ... 构建 HTML ...
```

### 5.7 报告生成模块 (reporter.py)

**职责**：生成 HTML 格式的测试报告

#### 报告结构

```python
def _build_html(self, stats: dict) -> str:
    return f"""<!DOCTYPE html>
<html>
<head>
    <title>Regression Report</title>
    <style>
        {self._get_css()}
    </style>
</head>
<body>
    <h1>Regression Report</h1>

    <!-- 统计摘要 -->
    {self._build_stats_section(stats)}

    <!-- 用例详情 -->
    {self._build_cases_section()}

    <script>
        {self._get_javascript()}
    </script>
</body>
</html>"""
```

#### 统计计算

```python
def _calculate_stats(self) -> dict:
    total_cases = len(self.results)
    passed_cases = sum(1 for r in self.results.values() if r.passed)

    total_runs = sum(r.times for r in self.results.values())
    passed_runs = sum(r.pass_count for r in self.results.values())

    return {
        'total_cases': total_cases,
        'passed_cases': passed_cases,
        'case_pass_rate': (passed_cases / total_cases * 100) if total_cases > 0 else 0,
        # ...
    }
```

---

## 六、进阶知识点

### 6.1 多线程编程

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# 创建线程池
with ThreadPoolExecutor(max_workers=4) as executor:
    # 提交任务
    futures = [executor.submit(func, arg) for arg in args]

    # 按完成顺序获取结果
    for future in as_completed(futures):
        result = future.result()

# 线程锁
lock = threading.Lock()
with lock:
    # 临界区代码
    pass

# 事件 (用于线程间通信)
event = threading.Event()
event.set()      # 设置标志
event.is_set()   # 检查标志
event.wait()     # 阻塞等待
```

### 6.2 信号处理

```python
import signal

def handle_interrupt(signum, frame):
    print("Interrupted!")
    # 清理工作...

# 注册信号处理函数
signal.signal(signal.SIGINT, handle_interrupt)   # Ctrl+C
signal.signal(signal.SIGTERM, handle_interrupt)  # kill 命令
```

### 6.3 subprocess 模块

```python
import subprocess

# 方式1: 等待命令完成
result = subprocess.run(
    ['ls', '-la'],
    capture_output=True,  # 捕获输出
    text=True,            # 输出为字符串
    timeout=60            # 超时秒数
)
print(result.stdout)
print(result.returncode)

# 方式2: 后台运行
process = subprocess.Popen(
    ['make', 'sim'],
    stdout=subprocess.DEVNULL,  # 丢弃输出
    stderr=subprocess.DEVNULL
)
process.wait()  # 等待结束
process.kill()  # 强制终止
```

### 6.4 argparse 模块

```python
import argparse

parser = argparse.ArgumentParser(description="Regression Script")

# 添加参数
parser.add_argument('-j', '--jobs', type=int, help='Parallel jobs')
parser.add_argument('-d', '--debug', action='store_true', help='Debug mode')
parser.add_argument('--config', default='regress.cfg', help='Config file')

# 解析
args = parser.parse_args()
print(args.jobs)
print(args.debug)
```

---

## 七、命令行模式详解

### 8.1 命令预览模式 (`--show-commands` / `--dry-run`)

只打印将要执行的命令，不实际运行：

```python
# regr_run.py 中的 dry-run 实现
def _run_dry_run(self, config, modes, cases, timestamp):
    self.logger.info("Dry-run mode: printing commands")

    # 打印编译命令
    for mode in modes:
        cmd = compiler.build_compile_command(mode)
        self.logger.info("Compile %s:", mode)
        self.logger.info("  %s", ' '.join(cmd))

    # 打印仿真命令
    for case in cases:
        for run_id in range(1, case.times + 1):
            cmd = executor.build_sim_command(case, seed)
            self.logger.info("  %s", ' '.join(cmd))

    return 0  # 直接返回，不执行
```

**使用场景**：
- 验证命令正确性
- 检查参数传递
- 调试 Makefile 变量

### 8.2 编译模式 (`--compile-only`)

只编译不仿真：

```python
# regr_run.py 中
compiler.compile_all_modes(modes)

if config.compile_only:
    self.logger.info("Compile-only mode complete")
    return 0  # 结束
```

**使用场景**：
- 验证编译配置
- 预编译镜像供后续使用
- 排查编译错误

### 8.3 仿真模式 (`--sim-only` / `--skip-compile`)

跳过编译直接仿真：

```python
# config.py 中互斥检测
def validate(self):
    if self.compile_only and self.skip_compile:
        errors.append("--compile-only and --sim-only are mutually exclusive")

# regr_run.py 中
if config.skip_compile:
    self.logger.info("Skipping compilation (using existing simv)")
    # 检查 simv 是否存在
    for mode in modes:
        if not os.path.exists(simv_path):
            self.logger.error("simv not found")
            return 1
```

**使用场景**：
- 快速重跑已有镜像
- 单独测试某个用例
- 节省编译时间

### 8.4 错误处理示例

```python
# config.py 中
def validate(self) -> List[str]:
    errors = []

    # 文件存在检查
    if not os.path.exists(self.case_list):
        errors.append(f"Case list file not found: {self.case_list}")

    # 参数范围检查
    if self.jobs < 1:
        errors.append(f"jobs must be >= 1, got {self.jobs}")

    # 互斥参数检查
    if self.compile_only and self.skip_compile:
        errors.append("--compile-only and --sim-only are mutually exclusive")

    return errors
```

---

## 八、学习路线建议

### 7.1 推荐阅读顺序

1. **第一遍**：了解整体结构
   - `regr_run.py` (主入口)
   - `config.py` (配置管理)
   - `utils.py` (工具函数)

2. **第二遍**：理解数据处理
   - `case_parser.py` (用例解析)
   - `result_checker.py` (结果判定)

3. **第三遍**：深入核心逻辑
   - `compiler.py` (编译管理)
   - `executor.py` (并行执行 - 重点)

4. **第四遍**：学习报告生成
   - `reporter.py` (HTML 报告)

### 7.2 调试技巧

```bash
# 1. 使用 dry-run 模式，只打印命令不执行
python regr_run.py --dry-run

# 2. 启用 debug 模式
python regr_run.py -d

# 3. 只解析用例列表
python -c "
from regr.case_parser import CaseParser
parser = CaseParser()
cases = parser.parse('case.lst')
for case in cases:
    print(case)
"

# 4. 检查配置加载
python -c "
from regr.config import RegressionConfig
config = RegressionConfig.load(None)
print(config)
"
```

### 7.3 常见问题

**Q: 如何添加新的配置参数？**

1. 在 `RegressionConfig` 中添加字段
2. 在 `_load_from_file` 中添加映射
3. 在 `_override_from_args` 中添加覆盖逻辑

**Q: 如何自定义结果判定？**

修改 `fail_keywords` 和 `pass_keywords` 配置：
```
fail_keywords = UVM_FATAL|UVM_ERROR|TEST_FAIL
pass_keywords = TEST_PASS
```

**Q: 如何增加并行度？**

```bash
python regr_run.py -j 8  # 8 个并行任务
```

---

## 附录：常用 Python 模块速查

| 模块 | 用途 | 示例 |
|------|------|------|
| `os` | 操作系统接口 | `os.path.exists()`, `os.makedirs()` |
| `sys` | 系统参数 | `sys.argv`, `sys.exit()` |
| `pathlib` | 路径处理 | `Path('file').exists()` |
| `subprocess` | 执行命令 | `subprocess.run(['ls'])` |
| `argparse` | 命令行参数 | `parser.add_argument()` |
| `re` | 正则表达式 | `re.search(pattern, text)` |
| `threading` | 多线程 | `threading.Lock()` |
| `datetime` | 日期时间 | `datetime.now()` |
| `dataclasses` | 数据类 | `@dataclass` |
| `typing` | 类型注解 | `List[str]`, `Optional[int]` |

---

*文档版本: 1.1*
*最后更新: 2026-04-03*

## 更新日志

### v1.1 (2026-04-03)
- 补充 `--show-commands`、`--compile-only`、`--sim-only` 模式说明
- 添加 `status_tracker.py` 模块解读
- 更新 `executor.py` 中的 StatusTracker 集成说明
- 添加运行态 HTML 报告刷新机制说明

### v1.0 (2026)
- 初版发布
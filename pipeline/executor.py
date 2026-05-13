"""goose CLI 调用封装 — 实时输出、看门狗超时、日志捕获。"""

import os
import sys
import time
import shutil
import logging
import threading
import subprocess
from pathlib import Path

from pipeline.watchdog import ProcessWatchdog

logger = logging.getLogger("ai-dev-flow")

HEARTBEAT_INTERVAL = 60


class GooseError(Exception):
    def __init__(self, returncode: int, stderr: str = ""):
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(f"goose exited with code {returncode}")


class GooseNotFound(Exception):
    pass


def check_goose() -> str:
    goose = shutil.which("goose")
    if not goose:
        raise GooseNotFound(
            "goose CLI not found in PATH.\n"
            "Install: https://block.github.io/goose/"
        )
    logger.debug(f"goose found: {goose}")
    return goose


def build_params(params: dict[str, str]) -> list[str]:
    """构建 goose --params 参数列表。值含 YAML 特殊字符时自动加引号。"""
    result = []
    for key, value in params.items():
        # goose 可能将 --params key=value 解析为 YAML，
        # 若 value 含 : # { } [ ] , & * ? | > < ! % @ ` 等字符则加引号
        if _needs_yaml_quoting(value):
            value = f'"{value}"'
        result.extend(["--params", f"{key}={value}"])
    return result


def _needs_yaml_quoting(value: str) -> bool:
    """检查字符串是否包含需要 YAML 引号的特殊字符。"""
    for ch in value:
        if ch in ':#{}[]&*?!|>%@`,' or ch == '"':
            return True
    return False


def _build_args(recipe: str, max_turns: int, params: dict[str, str], quiet: bool = False) -> list[str]:
    args = [
        "goose", "run",
        "--recipe", recipe,
        "--max-turns", str(max_turns),
    ]
    if quiet:
        args.append("-q")
    args.extend(build_params(params))
    return args


def _spawn(args: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.Popen:
    """启动 goose 子进程，捕获 stdout/stderr 管道。env 合并入子进程环境。"""
    proc_env = None
    if env:
        proc_env = {**os.environ, **env}
    try:
        return subprocess.Popen(
            args,
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=proc_env,
        )
    except FileNotFoundError:
        raise GooseNotFound("goose CLI not found in PATH")


def _probe_process(pid: int) -> str:
    """查询进程状态用于诊断。返回简短描述字符串。

    用 tasklist /V 获取 Status (Running/Not Responding) 和 CPU Time，
    辅助判断是 API I/O 阻塞还是 CPU 死循环。
    """
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/V", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=5,
        )
        line = result.stdout.strip()
        if not line or str(pid) not in line:
            return "state=exited"
        parts = [p.strip().strip('"') for p in line.split(",")]
        if len(parts) < 8:
            return "state=parse_error"
        # parts: 0=Name, 1=PID, 2=Session, 3=Session#, 4=Mem, 5=Status, 6=User, 7=CPU_Time
        status = parts[5]
        mem = parts[4]
        cpu_time = parts[7] if len(parts) > 7 else "N/A"
        classification = _classify_state(status, cpu_time)
        return f"state={classification} status={status} mem={mem} cpu_time={cpu_time}"
    except Exception:
        return "state=unknown"


def _classify_state(status: str, cpu_time: str) -> str:
    """基于进程状态和 CPU 时间推断卡死原因。"""
    if status == "Not Responding":
        return "IO_wait(API_hang?)"
    if cpu_time and cpu_time != "0:00:00":
        return "CPU_busy(loop?)"
    return "idle"


def _run_with_watchdog(
    args: list[str],
    cwd: Path,
    timeout_seconds: int | None,
    on_timeout=None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """核心执行逻辑：线程化 I/O + 可选的看门狗超时控制。

    env 注入自定义环境变量（如 JAVA_HOME）到 goose 子进程。
    """

    proc = _spawn(args, cwd, env=env)

    stderr_lines: list[str] = []
    stdout_lines: list[str] = []
    heartbeat = {"last": time.time()}

    def _read_stdout():
        for raw_line in proc.stdout:
            line = raw_line.rstrip()
            if line:
                stdout_lines.append(line)
                print(line, flush=True)
                logger.debug(f"[goose] {line}")
                heartbeat["last"] = time.time()

    def _read_stderr():
        for line in proc.stderr:
            stripped = line.rstrip()
            if stripped:
                stderr_lines.append(stripped)
                logger.warning(f"[goose] {stripped}")
                heartbeat["last"] = time.time()

    stdout_thread = threading.Thread(target=_read_stdout, daemon=True)
    stderr_thread = threading.Thread(target=_read_stderr, daemon=True)
    stdout_thread.start()
    stderr_thread.start()

    # 看门狗（可选）
    watchdog = None
    if timeout_seconds and timeout_seconds > 0:
        watchdog = ProcessWatchdog(proc.pid, timeout_seconds, on_timeout=on_timeout)
        watchdog.start()

    # 心跳日志（含进程状态诊断）
    def _heartbeat_loop():
        while proc.poll() is None:
            elapsed = time.time() - heartbeat["last"]
            if elapsed > HEARTBEAT_INTERVAL:
                info = _probe_process(proc.pid)
                logger.warning(
                    f"Goose has produced no output for {int(elapsed)}s (pid={proc.pid}, {info})"
                )
            time.sleep(min(HEARTBEAT_INTERVAL, 30))

    heartbeat_thread = threading.Thread(target=_heartbeat_loop, daemon=True)
    heartbeat_thread.start()

    # 主线程等待进程退出（有超时，防止 taskkill 失败导致永久卡死）
    if timeout_seconds:
        try:
            proc.wait(timeout=timeout_seconds + 30)
        except subprocess.TimeoutExpired:
            logger.critical(f"Process {proc.pid} survived watchdog, force killing")
            proc.kill()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.critical(f"Process {proc.pid} UNKILLABLE")
    else:
        proc.wait()

    # 看门狗取消
    if watchdog:
        watchdog.cancel()

    # 等待 I/O 线程结束
    stdout_thread.join(timeout=5)
    stderr_thread.join(timeout=5)

    # 收集结果
    stderr_text = "\n".join(stderr_lines)

    if watchdog and watchdog.triggered:
        return subprocess.CompletedProcess(
            args=args, returncode=-1,
            stdout="", stderr=f"Process killed by watchdog after {timeout_seconds}s"
        )

    if proc.returncode != 0:
        logger.error(f"goose exited with code {proc.returncode}")

    return subprocess.CompletedProcess(
        args=args,
        returncode=proc.returncode,
        stdout="",
        stderr=stderr_text,
    )


def run_stage(
    recipe: str,
    max_turns: int,
    params: dict[str, str],
    cwd: Path | None = None,
    timeout_minutes: int | None = None,
    quiet: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """执行 goose recipe 阶段。

    timeout_minutes=None 时无超时限制（阶段级执行），>0 时启用心跳看门狗。
    quiet=True 时传 -q 给 goose，隐藏文件扫描噪音，仅显示模型回复。
    env 注入自定义环境变量（如 JAVA_HOME）。
    """
    recipe_path = Path(recipe)
    args = _build_args(str(recipe_path), max_turns, params, quiet=quiet)

    logger.info(f"goose run --recipe {recipe_path.name} --max-turns {max_turns}" +
                (" -q" if quiet else ""))
    logger.debug(f"stage params: {params}")

    timeout_secs = (timeout_minutes * 60) if timeout_minutes else None
    return _run_with_watchdog(args, cwd or Path.cwd(), timeout_secs, env=env)


def run_task(
    recipe: str,
    max_turns: int,
    params: dict[str, str],
    cwd: Path,
    timeout_minutes: int = 15,
    on_timeout=None,
    quiet: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """执行单个任务。与 run_stage 相同流程，但始终启用心跳看门狗超时控制。

    on_timeout 在进程被看门狗终止后调用（用于沙箱清理等）。
    quiet=True 时传 -q 给 goose，隐藏文件扫描噪音，仅显示模型回复。
    env 注入自定义环境变量（如 JAVA_HOME）。
    """
    recipe_path = Path(recipe)
    args = _build_args(str(recipe_path), max_turns, params, quiet=quiet)

    logger.info(f"task: goose run --recipe {recipe_path.name} --max-turns {max_turns}" +
                (" -q" if quiet else ""))
    logger.debug(f"task params: {params}")
    logger.debug(f"goose args: {args}")

    return _run_with_watchdog(args, cwd, timeout_minutes * 60, on_timeout=on_timeout, env=env)


class JdkNotFound(Exception):
    """未找到匹配版本的 JDK。"""
    def __init__(self, required: int, searched: list[str]):
        self.required = required
        self.searched = searched
        msg = (
            f"未找到 JDK {required}。已搜索:\n" +
            "\n".join(f"  - {p}" for p in searched) +
            f"\n请安装 JDK {required} 或设置 JAVA_HOME 环境变量。"
        )
        super().__init__(msg)


def detect_jdk(required_version: int = 17) -> str:
    """扫描系统找到匹配主版本的 JDK，返回 JAVA_HOME 路径。

    搜索顺序：D 盘 Azul Zulu → common JDK 路径 → PATH 中的 javac。
    找不到则抛出 JdkNotFound。
    """
    search_roots = [
        # D 盘常见路径
        Path("D:/"),
        # 系统盘常见路径
        Path("C:/Program Files/Eclipse Adoptium"),
        Path("C:/Program Files/Java"),
    ]

    javac_paths: list[Path] = []

    # 1. 扫描已知安装目录
    for root in search_roots:
        if not root.exists():
            continue
        if root.name == "D:/" or root == Path("D:/"):
            # 扫描 D 盘根目录下的 JDK 目录
            for d in root.iterdir():
                if d.is_dir() and ("jdk" in d.name.lower() or "zulu" in d.name.lower()):
                    javac = d / "bin" / "javac.exe"
                    if javac.exists():
                        javac_paths.append(javac)
        else:
            for d in root.glob("jdk*"):
                javac = d / "bin" / "javac.exe"
                if javac.exists():
                    javac_paths.append(javac)
            for d in root.glob("*"):
                if d.is_dir():
                    javac = d / "bin" / "javac.exe"
                    if javac.exists():
                        javac_paths.append(javac)

    # 2. PATH 中的 javac
    import shutil as _shutil
    path_javac = _shutil.which("javac")
    if path_javac:
        javac_paths.append(Path(path_javac))

    # 3. 逐个检查版本
    seen = set()
    for javac in javac_paths:
        javac = javac.resolve()
        key = str(javac)
        if key in seen:
            continue
        seen.add(key)
        try:
            proc = subprocess.run(
                [str(javac), "-version"],
                capture_output=True, text=True, timeout=10,
            )
            output = proc.stdout + proc.stderr
            version_str = _parse_javac_version(output)
            if version_str and version_str[0] == required_version:
                java_home = str(javac.parent.parent)
                logger.info(f"JDK {required_version} detected: {java_home} (v{'.'.join(map(str, version_str))})")
                return java_home
        except Exception:
            continue

    raise JdkNotFound(required_version, [str(p) for p in javac_paths])


def _parse_javac_version(output: str) -> tuple[int, ...] | None:
    """从 javac -version 输出中提取版本号。如 'javac 17.0.13' → (17, 0, 13)。"""
    import re
    m = re.search(r'(\d+)\.(\d+)(?:\.(\d+))?', output)
    if m:
        return tuple(int(x) for x in m.groups() if x is not None)
    return None

"""goose CLI 调用封装 — 实时输出、看门狗超时、日志捕获。"""

import os
import csv
import sys
import time
import shutil
import logging
import threading
import subprocess
from collections import deque
from pathlib import Path

from pipeline.watchdog import ProcessWatchdog

logger = logging.getLogger("ai-dev-flow")

HEARTBEAT_INTERVAL = 60
DEFAULT_STAGE_TIMEOUT_MINUTES = 30
DEFAULT_IDLE_TIMEOUT_SECONDS = 10 * 60
IDLE_TIMEOUT_RETURN_CODE = -2


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
    """检查 YAML 标量值是否需要引号包裹。

    跳过合法的 YAML flow sequence/mapping ([] 或 {})，其余含特殊字符的值需加引号。
    """
    import re as _re
    stripped = value.strip()
    if _re.match(r'^\[.*?\]$', stripped) or _re.match(r'^\{.*?\}$', stripped):
        return False
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
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip().splitlines()
            msg = detail[-1] if detail else f"exit={result.returncode}"
            return f"state=probe_error detail={msg[:80]}"
        line = result.stdout.strip()
        if not line or str(pid) not in line:
            return "state=exited"
        rows = list(csv.reader(line.splitlines()))
        if not rows:
            return "state=parse_error"
        parts = [p.strip() for p in rows[0]]
        if len(parts) < 8:
            return "state=parse_error"
        # tasklist /V CSV columns:
        # 0=Name, 1=PID, 2=Session, 3=Session#, 4=Mem, 5=Status,
        # 6=User, 7=CPU_Time, 8=WindowTitle. Use csv.reader because
        # localized memory values may contain commas, e.g. "1,428 K".
        status = parts[5] if len(parts) > 5 else "unknown"
        mem = parts[4] if len(parts) > 4 else "unknown"
        cpu_time = parts[7] if len(parts) > 7 else "unknown"
        classification = _classify_state(status, cpu_time)
        return f"state={classification} status={status} mem={mem} cpu_time={cpu_time}"
    except Exception:
        return "state=unknown"


def _classify_state(status: str, cpu_time: str) -> str:
    """基于进程状态做保守诊断，避免把历史 CPU 时间误判成循环。"""
    normalized_status = (status or "").strip().lower()
    if normalized_status == "not responding":
        return "not_responding"
    if _cpu_time_to_seconds(cpu_time) > 0:
        return "running_cpu_seen"
    return "running_no_cpu_seen"


def _cpu_time_to_seconds(cpu_time: str) -> int:
    """将 tasklist CPU Time 转为秒。解析失败返回 0。"""
    if not cpu_time:
        return 0
    parts = cpu_time.strip().split(":")
    if len(parts) != 3:
        return 0
    try:
        hours, minutes, seconds = (int(p) for p in parts)
    except ValueError:
        return 0
    return hours * 3600 + minutes * 60 + seconds


def _kill_process_tree(pid: int) -> None:
    """强制终止进程树。用于静默超时和循环检测。"""
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True, text=True, timeout=10,
            )
        except Exception:
            logger.exception("taskkill failed")
    else:
        try:
            import signal
            os.kill(pid, signal.SIGKILL)
        except Exception:
            logger.exception("kill failed")


def _run_with_watchdog(
    args: list[str],
    cwd: Path,
    timeout_seconds: int | None,
    on_timeout=None,
    env: dict[str, str] | None = None,
    idle_timeout_seconds: int | None = None,
) -> subprocess.CompletedProcess:
    """核心执行逻辑：线程化 I/O + 可选的看门狗超时控制。

    env 注入自定义环境变量（如 JAVA_HOME）到 goose 子进程。
    """

    proc = _spawn(args, cwd, env=env)

    stderr_lines: list[str] = []
    stdout_lines: list[str] = []
    heartbeat = {"last": time.time()}
    recent_stderr: deque[str] = deque(maxlen=10)  # 最近 stderr 行，用于循环检测
    idle_kill = {"triggered": False, "elapsed": 0, "info": ""}

    def _read_stdout():
        for raw_line in proc.stdout:
            line = raw_line.rstrip()
            if line:
                stdout_lines.append(line)
                logger.debug(f"[goose] {line}")
                heartbeat["last"] = time.time()

    def _read_stderr():
        for line in proc.stderr:
            stripped = line.rstrip()
            if stripped:
                stderr_lines.append(stripped)
                recent_stderr.append(stripped)
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

    # 心跳日志（含进程状态诊断 + 循环检测）
    LOOP_DETECT_THRESHOLD = 5  # 连续相同 stderr 行 >= 5 次视为循环
    _loop_warning_count = 0

    def _heartbeat_loop():
        nonlocal _loop_warning_count
        while proc.poll() is None:
            elapsed = time.time() - heartbeat["last"]
            if elapsed > HEARTBEAT_INTERVAL:
                info = _probe_process(proc.pid)
                logger.warning(
                    f"Goose has produced no output for {int(elapsed)}s (pid={proc.pid}, {info})"
                )
            if idle_timeout_seconds and elapsed > idle_timeout_seconds:
                info = _probe_process(proc.pid)
                idle_kill["triggered"] = True
                idle_kill["elapsed"] = int(elapsed)
                idle_kill["info"] = info
                logger.critical(
                    f"Goose idle timeout after {int(elapsed)}s without output "
                    f"(limit={idle_timeout_seconds}s, pid={proc.pid}, {info}); killing process tree"
                )
                _kill_process_tree(proc.pid)
                if proc.poll() is None:
                    proc.kill()
                break
            # 循环检测：最近 N 行 stderr 全部相同 → 卡死在重试循环
            if len(recent_stderr) >= LOOP_DETECT_THRESHOLD:
                recent_list = list(recent_stderr)
                if all(line == recent_list[-1] for line in recent_list[-LOOP_DETECT_THRESHOLD:]):
                    _loop_warning_count += 1
                    if _loop_warning_count >= 3:
                        logger.critical(
                            f"Goose appears stuck in a retry loop (same stderr {LOOP_DETECT_THRESHOLD}x): "
                            f"{recent_list[-1][:200]}"
                        )
                        _kill_process_tree(proc.pid)
                        if proc.poll() is None:
                            proc.kill()
                        break
            sleep_for = min(HEARTBEAT_INTERVAL, 30)
            if idle_timeout_seconds:
                sleep_for = min(sleep_for, max(0.2, idle_timeout_seconds / 4))
            time.sleep(sleep_for)

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

    if idle_kill["triggered"]:
        return subprocess.CompletedProcess(
            args=args,
            returncode=IDLE_TIMEOUT_RETURN_CODE,
            stdout="",
            stderr=(
                f"Process killed after {idle_kill['elapsed']}s without goose output "
                f"(idle limit {idle_timeout_seconds}s; {idle_kill['info']})"
            ),
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
    timeout_minutes: int | None = DEFAULT_STAGE_TIMEOUT_MINUTES,
    quiet: bool = True,
    env: dict[str, str] | None = None,
    idle_timeout_seconds: int | None = DEFAULT_IDLE_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess:
    """执行 goose recipe 阶段。

    默认启用阶段级硬超时和静默超时，防止 goose 阶段无限等待。
    timeout_minutes=None 或 0 表示禁用硬超时。
    idle_timeout_seconds=None 或 0 表示禁用静默超时。
    quiet=True 时传 -q 给 goose，隐藏文件扫描噪音，仅显示模型回复。
    env 注入自定义环境变量（如 JAVA_HOME）。
    """
    recipe_path = Path(recipe)
    args = _build_args(str(recipe_path), max_turns, params, quiet=quiet)

    logger.info(f"goose run --recipe {recipe_path.name} --max-turns {max_turns}" +
                (" -q" if quiet else ""))
    logger.debug(f"stage params: {params}")

    timeout_secs = (timeout_minutes * 60) if timeout_minutes else None
    return _run_with_watchdog(
        args, cwd or Path.cwd(), timeout_secs, env=env,
        idle_timeout_seconds=idle_timeout_seconds,
    )


def run_task(
    recipe: str,
    max_turns: int,
    params: dict[str, str],
    cwd: Path,
    timeout_minutes: int = 15,
    on_timeout=None,
    quiet: bool = True,
    env: dict[str, str] | None = None,
    idle_timeout_seconds: int | None = DEFAULT_IDLE_TIMEOUT_SECONDS,
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

    return _run_with_watchdog(
        args, cwd, timeout_minutes * 60, on_timeout=on_timeout, env=env,
        idle_timeout_seconds=idle_timeout_seconds,
    )


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

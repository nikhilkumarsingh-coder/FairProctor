"""Compile, run and judge candidate code: Python 3, C++17, Java 17+, JavaScript (Node).

Each run happens in a fresh temporary folder with:
  * a CPU-time limit and a wall-clock timeout (the whole process group is killed),
  * a memory limit (address space for Python/C++, heap flags for Java/Node),
  * an output limit (stdout goes to a file capped at OUTPUT_LIMIT bytes),
  * a clean environment, and on Linux as root: the unprivileged "nobody" user and a process-count limit.

This is a reasonable sandbox for a test platform on its own container (Render, Docker). It does not cut the
network, so for a large public deployment put the runs behind a jail such as isolate/nsjail or Judge0.
On Windows (local development) only the timeouts and output cap apply.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field

POSIX = os.name == "posix"
if POSIX:
    import resource
    import signal

OUTPUT_LIMIT = 64 * 1024          # bytes of stdout kept per run
FILE_LIMIT = 1024 * 1024          # bytes a program may write to any file (POSIX)
MEMORY_MB = 256
COMPILE_TIMEOUT = 25.0
MAX_CODE = 64 * 1024              # characters
_slots = threading.BoundedSemaphore(int(os.environ.get("FP_RUNNER_SLOTS", "2")))   # runs at the same time


@dataclass
class Lang:
    key: str
    label: str
    file: str
    compile: list[str] | None
    run: list[str]
    needs: list[str]
    extra_seconds: float = 0.0            # start-up time on top of the problem's limit (JVM, Node)
    limit_address_space: bool = True      # JVM / V8 reserve far more virtual memory than they use


def _exe(name: str) -> str:
    return name + (".exe" if os.name == "nt" else "")


LANGS: dict[str, Lang] = {
    "python": Lang("python", "Python 3", "main.py", None, [sys.executable, "-I", "main.py"], []),
    "cpp": Lang("cpp", "C++17 (g++)", "main.cpp", ["g++", "-O2", "-std=c++17", "-pipe", "-o", _exe("main"), "main.cpp"],
                [os.path.join(".", _exe("main"))], ["g++"]),
    "java": Lang("java", "Java", "Main.java", ["javac", "-encoding", "UTF-8", "-J-Xmx256m", "Main.java"],
                 ["java", f"-Xmx{MEMORY_MB}m", "-Xss64m", "-XX:+UseSerialGC", "-XX:TieredStopAtLevel=1", "-XX:-UsePerfData", "Main"],
                 ["javac", "java"], extra_seconds=1.0, limit_address_space=False),
    "javascript": Lang("javascript", "JavaScript (Node)", "main.js", None, ["node", f"--max-old-space-size={MEMORY_MB}", "main.js"],
                       ["node"], extra_seconds=0.5, limit_address_space=False),
}


def available() -> dict[str, bool]:
    """Which languages this server can run (a compiler missing on a laptop just turns that language off)."""
    return {k: all(shutil.which(n) for n in L.needs) for k, L in LANGS.items()}


def languages() -> list[dict]:
    av = available()
    return [dict(key=k, label=L.label, available=av[k]) for k, L in LANGS.items()]


@dataclass
class RunResult:
    status: str                 # ok | runtime_error | time_limit | output_limit | memory_limit
    stdout: str = ""
    stderr: str = ""
    seconds: float = 0.0
    exit_code: int | None = None


@dataclass
class Verdict:
    verdict: str                # accepted | wrong_answer | compile_error | runtime_error | time_limit | output_limit
    passed: int = 0
    total: int = 0
    compile_output: str = ""
    tests: list[dict] = field(default_factory=list)
    seconds: float = 0.0


def _env(tmp: str) -> dict:
    env = {"PATH": os.environ.get("PATH", ""), "HOME": tmp, "TMPDIR": tmp, "LANG": "C.UTF-8", "PYTHONIOENCODING": "utf-8"}
    if os.name == "nt":                                   # Windows needs these for compilers and node to start
        for k in ("SYSTEMROOT", "SYSTEMDRIVE", "TEMP", "TMP", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PATHEXT", "COMSPEC"):
            if k in os.environ:
                env[k] = os.environ[k]
    return env


# Runs before the candidate's program (as a tiny separate process, because preexec_fn is unsafe in a threaded
# server): sets the limits, drops to "nobody" when started as root, then replaces itself with the program.
LAUNCHER = """
import os, resource, sys
cpu, aspace, drop, fsize, mem = int(sys.argv[1]), sys.argv[2] == "1", sys.argv[3] == "1", int(sys.argv[4]), int(sys.argv[5])
resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
resource.setrlimit(resource.RLIMIT_FSIZE, (fsize, fsize))
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
if aspace:
    resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
if drop:
    resource.setrlimit(resource.RLIMIT_NPROC, (256, 256))
    os.setgroups([])
    os.setgid(65534)
    os.setuid(65534)
os.execvp(sys.argv[7], sys.argv[7:])
"""


def _wrap(cmd: list[str], cpu_seconds: float, address_space: bool, drop: bool) -> list[str]:
    mem = (MEMORY_MB + 64) * 1024 * 1024
    return [sys.executable, "-I", "-S", "-c", LAUNCHER, str(int(cpu_seconds) + 1), "1" if address_space else "0",
            "1" if drop else "0", str(FILE_LIMIT), str(mem), "--", *cmd]


def _run(cmd: list[str], cwd: str, stdin_text: str, timeout: float, address_space: bool, cpu: float) -> RunResult:
    drop = POSIX and os.geteuid() == 0
    inp = os.path.join(cwd, ".stdin")
    out = os.path.join(cwd, ".stdout")
    err = os.path.join(cwd, ".stderr")
    with open(inp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(stdin_text)
    t0 = time.monotonic()
    with open(inp, "rb") as fi, open(out, "wb") as fo, open(err, "wb") as fe:
        kw = dict(cwd=cwd, stdin=fi, stdout=fo, stderr=fe, env=_env(cwd))
        if POSIX:
            kw["start_new_session"] = True              # own process group, so a timeout kills every child
            cmd = _wrap(cmd, cpu, address_space, drop)
        else:
            kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            p = subprocess.Popen(cmd, **kw)
        except OSError as e:
            return RunResult("runtime_error", stderr=f"could not start: {e}")
        timed_out = False
        try:
            p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill(p)
            p.wait()
    took = time.monotonic() - t0
    size = os.path.getsize(out)
    with open(out, "rb") as fh:
        stdout = fh.read(OUTPUT_LIMIT).decode("utf-8", "replace")
    with open(err, "rb") as fh:
        stderr = fh.read(4000).decode("utf-8", "replace")
    code = p.returncode
    if timed_out or (POSIX and code in (-signal.SIGXCPU, -signal.SIGKILL) and took >= cpu * 0.9):
        return RunResult("time_limit", stdout, stderr, took, code)
    if size > OUTPUT_LIMIT or (POSIX and code == -signal.SIGXFSZ):
        return RunResult("output_limit", stdout, stderr, took, code)
    if code != 0:
        mem = "MemoryError" in stderr or "OutOfMemoryError" in stderr or "bad_alloc" in stderr or "heap out of memory" in stderr
        return RunResult("memory_limit" if mem else "runtime_error", stdout, stderr, took, code)
    return RunResult("ok", stdout, stderr, took, code)


def _kill(p: subprocess.Popen):
    try:
        if POSIX:
            os.killpg(p.pid, signal.SIGKILL)
        else:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
    except (ProcessLookupError, PermissionError, OSError):
        p.kill()


def normalise(text: str) -> str:
    """Compare outputs ignoring trailing spaces on each line and trailing blank lines (\\r\\n from Windows too)."""
    lines = [ln.rstrip() for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


class Workspace:
    """A temporary folder holding one compiled program, reused for every test case of one submission."""

    def __init__(self, language: str, code: str):
        if language not in LANGS:
            raise ValueError(f"unknown language {language}")
        self.L = LANGS[language]
        self.code = code
        self.dir = tempfile.mkdtemp(prefix="fp-run-")
        if POSIX and os.geteuid() == 0:
            os.chmod(self.dir, 0o777)                    # the unprivileged user must be able to write here
        with open(os.path.join(self.dir, self.L.file), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(code)

    def compile(self) -> str | None:
        """None if it compiled, else the compiler's message (paths removed)."""
        if not self.L.compile:
            return None
        try:
            r = subprocess.run(self.L.compile, cwd=self.dir, capture_output=True, timeout=COMPILE_TIMEOUT, env=_env(self.dir))
        except subprocess.TimeoutExpired:
            return "Compilation took too long."
        except OSError as e:
            return f"Compiler not available on this server: {e}"
        if r.returncode != 0:
            msg = (r.stderr or r.stdout).decode("utf-8", "replace").replace(self.dir + os.sep, "").replace(self.dir, "")
            return msg[:3000] or "Compilation failed."
        if POSIX and os.geteuid() == 0:
            for f in os.listdir(self.dir):
                os.chmod(os.path.join(self.dir, f), 0o777)
        return None

    def run(self, stdin_text: str, time_limit: float) -> RunResult:
        timeout = time_limit + self.L.extra_seconds
        return _run(self.L.run, self.dir, stdin_text, timeout=timeout * 2 + 0.5,
                    address_space=self.L.limit_address_space, cpu=timeout)

    def close(self):
        shutil.rmtree(self.dir, ignore_errors=True)


def judge(language: str, code: str, tests: list[dict], time_limit: float, show: bool, stop_on_fail: bool = False) -> Verdict:
    """Run every test {input, expected}; `show` returns inputs/outputs (sample tests only, never hidden ones)."""
    if len(code) > MAX_CODE:
        return Verdict("compile_error", 0, len(tests), compile_output=f"The code is longer than {MAX_CODE} characters.")
    if not available().get(language):
        return Verdict("compile_error", 0, len(tests), compile_output=f"{LANGS[language].label} is not installed on this server.")
    t0 = time.monotonic()
    with _slots:
        ws = Workspace(language, code)
        try:
            msg = ws.compile()
            if msg is not None:
                return Verdict("compile_error", 0, len(tests), compile_output=msg, seconds=time.monotonic() - t0)
            out, passed, first_fail = [], 0, None
            for i, tc in enumerate(tests):
                r = ws.run(tc["input"], time_limit)
                ok = r.status == "ok" and normalise(r.stdout) == normalise(tc["expected"])
                status = "passed" if ok else ("wrong_answer" if r.status == "ok" else r.status)
                passed += ok
                if not ok and first_fail is None:
                    first_fail = status
                row = dict(n=i + 1, status=status, seconds=round(r.seconds, 3))
                if show:
                    row.update(input=tc["input"][:2000], expected=tc["expected"][:2000], output=r.stdout[:2000], stderr=r.stderr[:1500])
                out.append(row)
                if stop_on_fail and not ok:
                    break
        finally:
            ws.close()
    verdict = "accepted" if passed == len(tests) and tests else (first_fail or "wrong_answer")
    if verdict == "memory_limit":
        verdict = "runtime_error"
    return Verdict(verdict, passed, len(tests), tests=out, seconds=round(time.monotonic() - t0, 2))


def run_custom(language: str, code: str, stdin_text: str, time_limit: float) -> dict:
    """'Run with my own input': compile + one run, output shown as is."""
    if not available().get(language):
        return dict(status="compile_error", compile_output=f"{LANGS[language].label} is not installed on this server.")
    if len(code) > MAX_CODE:
        return dict(status="compile_error", compile_output=f"The code is longer than {MAX_CODE} characters.")
    with _slots:
        ws = Workspace(language, code)
        try:
            msg = ws.compile()
            if msg is not None:
                return dict(status="compile_error", compile_output=msg)
            r = ws.run(stdin_text, time_limit)
            return dict(status=r.status, output=r.stdout[:8000], stderr=r.stderr[:2000], seconds=round(r.seconds, 3))
        finally:
            ws.close()

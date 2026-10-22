"""Measure server and Bot CPU on Linux while verifying paced IPv6 IRC traffic."""

from pathlib import Path
import argparse
import hashlib
import json
import os
import platform
import queue
import shutil
import socket
import subprocess
import threading
import time
import sys

ROOT = Path(__file__).resolve().parents[1]
# Direct script execution needs the project root before local imports.
sys.path.insert(0, str(ROOT))
from common.irc_message import message  # noqa: E402
from common.stream import IRCStreamDecoder  # noqa: E402

PORT = 16667


def cpu_samples(output: str, pid: int) -> list[float]:
    values = []
    columns = None
    for line in output.splitlines():
        fields = line.split()
        if "PID" in fields and "%CPU" in fields:
            # Right offsets accommodate both 24-hour and AM/PM timestamps.
            columns = (
                fields.index("PID") - len(fields),
                fields.index("%CPU") - len(fields),
            )
        elif columns and len(fields) >= max(-index for index in columns):
            pid_index, cpu_index = columns
            if fields[pid_index] == str(pid):
                values.append(float(fields[cpu_index]))
    return values


class Client:
    def __init__(self, nick):
        self.nick = nick
        self.sock = socket.socket(socket.AF_INET6)
        self.send_lock = threading.Lock()
        self.messages = queue.Queue()
        self.error = None
        self.stop = threading.Event()
        self.reader = threading.Thread(target=self.read, daemon=True)
        try:
            self.sock.settimeout(1)
            self.sock.connect(("::1", PORT))
            self.reader.start()
            self.send("NICK", nick)
            self.send("USER", nick, "0", "*", nick)
            self.wait("001")
            self.send("JOIN", "#cpucheck")
            self.wait("366")
        except BaseException:
            self.close()
            raise

    def send(self, command, *params):
        with self.send_lock:
            self.sock.sendall(message(command, *params).to_bytes())

    def read(self):
        decoder = IRCStreamDecoder()
        try:
            while not self.stop.is_set():
                try:
                    data = self.sock.recv(4096)
                except socket.timeout:
                    continue
                if not data:
                    break
                for incoming in decoder.feed(data):
                    if incoming.command == "PING":
                        self.send("PONG", *incoming.params)
                    else:
                        self.messages.put(incoming)
        except Exception as exc:
            if not self.stop.is_set():
                self.error = str(exc)

    def wait(self, command, text=None):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                item = self.messages.get(timeout=0.2)
            except queue.Empty:
                continue
            if item.command == command and (text is None or text in item.params[-1]):
                return item
        raise TimeoutError(
            f"{self.nick}: missing {command} {text}, reader error={self.error}"
        )

    def close(self):
        self.stop.set()
        try:
            self.send("QUIT", "CPU test complete")
        except OSError:
            pass
        self.sock.close()
        if self.reader.is_alive():
            self.reader.join(timeout=2)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "cpu_evidence")
    parser.add_argument(
        "--source-archive",
        type=Path,
        help="Optional archive to identify alongside the measured sources",
    )
    args = parser.parse_args(argv)
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    processes, clients, handles, samplers = [], [], [], []
    result = {
        "environment": platform.platform(),
        "topology": "IPv6 ::1; two synthetic clients and one Bot",
        "python": sys.version,
        "seconds": 60,
        "interval_seconds": 1,
        "cpu_basis": "pidstat %CPU without -I; 100% means one logical CPU",
        "commands_per_second": 8,
        "validated_rounds": 0,
    }
    try:
        result["source_sha256"] = {
            path.relative_to(ROOT).as_posix(): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for package in ("bot", "server", "common")
            for path in sorted((ROOT / package).rglob("*.py"))
        }
        result["source_sha256"]["bot/data/facts.txt"] = hashlib.sha256(
            (ROOT / "bot/data/facts.txt").read_bytes()
        ).hexdigest()
        if args.source_archive:
            result["source_zip_sha256"] = hashlib.sha256(
                args.source_archive.read_bytes()
            ).hexdigest()
        if platform.system() != "Linux" or not shutil.which("pidstat"):
            raise RuntimeError("CPU measurement requires Linux and pidstat (sysstat)")
        for name, process_args in [
            ("server", ["-m", "server", "--host", "::1", "--port", str(PORT)]),
            (
                "bot",
                [
                    "-m",
                    "bot",
                    "--host",
                    "::1",
                    "--port",
                    str(PORT),
                    "--name",
                    "CpuBot",
                    "--channel",
                    "#cpucheck",
                ],
            ),
        ]:
            handle = (out / f"{name}.log").open("w")
            handles.append(handle)
            proc = subprocess.Popen(
                [sys.executable, *process_args], stdout=handle, stderr=handle, cwd=ROOT
            )
            processes.append(proc)
            time.sleep(1)
            if proc.poll() is not None:
                raise RuntimeError(f"{name} startup failed")
        alice = Client("CpuAlice")
        clients.append(alice)
        bob = Client("CpuBob")
        clients.append(bob)
        alice.send("PRIVMSG", "#cpucheck", "!hello")
        alice.wait("PRIVMSG", "Hello, CpuAlice!")
        for name, proc in zip(["server", "bot"], processes):
            handle = (out / f"{name}_pidstat.txt").open("w")
            handles.append(handle)
            env = dict(os.environ, LC_ALL="C")
            samplers.append(
                subprocess.Popen(
                    ["pidstat", "-h", "-p", str(proc.pid), "1", "60"],
                    stdout=handle,
                    stderr=handle,
                    env=env,
                )
            )
        start = time.monotonic()
        for index in range(60):
            alice.send("PRIVMSG", "#cpucheck", f"channel-{index}")
            bob.wait("PRIVMSG", f"channel-{index}")
            bob.send("PRIVMSG", "CpuAlice", f"private-{index}")
            alice.wait("PRIVMSG", f"private-{index}")
            for command, expected in [
                ("!hello", "Hello, CpuAlice!"),
                ("!time", "Bot time:"),
                ("!who", "WHO complete:"),
                ("!slap CpuBob", "CpuBob"),
            ]:
                alice.send("PRIVMSG", "#cpucheck", command)
                alice.wait("PRIVMSG", expected)
            alice.send("PRIVMSG", "CpuBot", "Tell me a fact")
            alice.wait("PRIVMSG")
            alice.send("PING", f"cpu-{index}")
            alice.wait("PONG", f"cpu-{index}")
            result["validated_rounds"] += 1
            time.sleep(max(0, start + index + 1 - time.monotonic()))
        for sampler in samplers:
            sampler.wait(timeout=10)
            if sampler.returncode:
                raise RuntimeError("pidstat failed")
        for handle in handles:
            handle.flush()
        for name, proc in zip(["server", "bot"], processes):
            values = cpu_samples((out / f"{name}_pidstat.txt").read_text(), proc.pid)
            if len(values) != 60:
                raise RuntimeError(f"{name}: expected 60 samples, got {len(values)}")
            result[name] = {
                "samples": len(values),
                "average_cpu_percent": round(sum(values) / len(values), 4),
                "max_cpu_percent": max(values),
                "passes_average_below_10": sum(values) / len(values) < 10,
            }
        result["status"] = (
            "PASS"
            if all(result[n]["passes_average_below_10"] for n in ["server", "bot"])
            else "FAIL"
        )
    except Exception as exc:
        result.update(status="FAIL", error=str(exc))
    finally:
        for client in clients:
            client.close()
        for proc in samplers + processes:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
        for handle in handles:
            handle.close()
        (out / "summary.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8"
        )
        print(json.dumps(result, indent=2), flush=True)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

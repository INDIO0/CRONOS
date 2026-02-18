import os
import shutil
import socket
import subprocess
import time

import psutil


class SystemMonitor:
    def __init__(self):
        self.thresholds = {
            "cpu": 90,
            "ram": 85,
            "disk": 90,
            "gpu": 90,
            "battery": 20,  # low-battery threshold (percent)
        }
        self.cooldown_sec = int(os.getenv("CRONO_MONITOR_COOLDOWN_SEC", "180"))
        self.cooldowns = {
            "cpu": int(os.getenv("CRONO_MONITOR_CPU_COOLDOWN_SEC", str(self.cooldown_sec))),
            "ram": int(os.getenv("CRONO_MONITOR_RAM_COOLDOWN_SEC", str(self.cooldown_sec))),
            "disk": int(os.getenv("CRONO_MONITOR_DISK_COOLDOWN_SEC", str(self.cooldown_sec))),
            "gpu": int(os.getenv("CRONO_MONITOR_GPU_COOLDOWN_SEC", str(self.cooldown_sec))),
            "battery": int(os.getenv("CRONO_MONITOR_BATTERY_COOLDOWN_SEC", "300")),
            "network": int(os.getenv("CRONO_MONITOR_NETWORK_COOLDOWN_SEC", "300")),
        }
        self._last_alert_at = {
            "cpu": 0.0,
            "ram": 0.0,
            "disk": 0.0,
            "gpu": 0.0,
            "battery": 0.0,
            "network": 0.0,
        }
        self._last_battery_bucket = None

    def get_stats(self) -> dict:
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        ram = mem.percent
        disk = psutil.disk_usage(self._disk_root()).percent
        gpu = self._gpu_percent()
        battery = self._battery_percent()
        network_online = self._network_online()

        proc_ram_mb = None
        proc_ram_pct = None
        try:
            proc = psutil.Process(os.getpid())
            rss = proc.memory_info().rss / (1024 * 1024)
            proc_ram_mb = float(rss)
            if mem.total:
                proc_ram_pct = (rss / (mem.total / (1024 * 1024))) * 100.0
        except Exception:
            pass

        return {
            "cpu": cpu,
            "ram": ram,
            "disk": disk,
            "gpu": gpu,
            "battery": battery,
            "network_online": network_online,
            "proc_ram_mb": proc_ram_mb,
            "proc_ram_pct": proc_ram_pct,
        }

    def format_status(self, stats: dict) -> str:
        cpu = int(round(stats.get("cpu", 0)))
        ram = int(round(stats.get("ram", 0)))
        disk = int(round(stats.get("disk", 0)))
        gpu = stats.get("gpu")
        battery = stats.get("battery")
        network_online = bool(stats.get("network_online", True))

        parts = [f"CPU {cpu}%", f"RAM {ram}%", f"Disco {disk}%"]
        if gpu is not None:
            parts.append(f"GPU {int(round(gpu))}%")
        if battery is not None:
            parts.append(f"Bateria {int(round(battery))}%")
        parts.append("Rede online" if network_online else "Rede offline")
        return ", ".join(parts) + "."

    def check_alerts(self, stats: dict) -> list[str]:
        alerts = []
        now = time.time()
        for key, threshold in self.thresholds.items():
            if key == "gpu" and stats.get("gpu") is None:
                continue
            if key == "battery":
                bat = stats.get("battery")
                if bat is None:
                    continue
                value = float(bat)
                triggered = value <= float(threshold)
            else:
                value = float(stats.get(key, 0))
                triggered = value >= float(threshold)

            if triggered:
                last = self._last_alert_at.get(key, 0.0)
                cooldown = float(self.cooldowns.get(key, self.cooldown_sec))
                if key == "battery":
                    # Only remind when entering a lower bucket (20/15/10/5/0)
                    bucket = self._battery_bucket(value)
                    if bucket is None:
                        self._last_battery_bucket = None
                    elif self._last_battery_bucket is None or bucket < self._last_battery_bucket:
                        self._last_battery_bucket = bucket
                        self._last_alert_at[key] = now
                        alerts.append(key)
                    elif now - last >= cooldown:
                        self._last_alert_at[key] = now
                        alerts.append(key)
                elif now - last >= cooldown:
                    self._last_alert_at[key] = now
                    alerts.append(key)
            elif key == "battery":
                # Battery recovered above threshold.
                self._last_battery_bucket = None

        if not bool(stats.get("network_online", True)):
            last = self._last_alert_at.get("network", 0.0)
            cooldown = float(self.cooldowns.get("network", self.cooldown_sec))
            if now - last >= cooldown:
                self._last_alert_at["network"] = now
                alerts.append("network")

        return alerts

    def alert_message(self, stats: dict, alerts: list[str]) -> str:
        parts = []
        if "cpu" in alerts:
            parts.append(f"CPU alta em {int(round(stats.get('cpu', 0)))} por cento")
        if "ram" in alerts:
            parts.append(f"RAM alta em {int(round(stats.get('ram', 0)))} por cento")
        if "disk" in alerts:
            parts.append(f"Disco alto em {int(round(stats.get('disk', 0)))} por cento")
        if "gpu" in alerts and stats.get("gpu") is not None:
            parts.append(f"GPU alta em {int(round(stats.get('gpu', 0)))} por cento")
        if "battery" in alerts:
            parts.append(f"bateria baixa em {int(round(stats.get('battery', 0)))} por cento")
        if "network" in alerts:
            parts.append("sem conexao com a internet")
        if not parts:
            return ""
        return "Atencao, " + ", ".join(parts) + "."

    def _battery_bucket(self, value: float):
        if value <= 5:
            return 5
        if value <= 10:
            return 10
        if value <= 15:
            return 15
        if value <= 20:
            return 20
        return None

    def _disk_root(self) -> str:
        if os.name == "nt":
            return os.path.abspath(os.sep)
        return "/"

    def _gpu_percent(self):
        try:
            if shutil.which("nvidia-smi"):
                result = subprocess.run(
                    ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                    capture_output=True,
                    text=True,
                    timeout=1.0,
                )
                if result.returncode == 0:
                    line = (result.stdout or "").strip().splitlines()
                    if line:
                        return float(line[0].strip())
        except Exception:
            pass
        return None

    def _battery_percent(self):
        try:
            batt = psutil.sensors_battery()
            if batt is None:
                return None
            return float(batt.percent)
        except Exception:
            return None

    def _network_online(self) -> bool:
        try:
            conn = socket.create_connection(("1.1.1.1", 53), timeout=1.2)
            conn.close()
            return True
        except Exception:
            return False

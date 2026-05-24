import os
import sys
import fcntl
import logging
import psutil
import subprocess
from functools import wraps

logger = logging.getLogger(__name__)

class BotInstanceManager:
    """
    Manages the lifecycle of the Telegram bot to prevent Conflict errors
    caused by multiple instances polling getUpdates simultaneously.
    """
    def __init__(self, lock_file="/tmp/jarvis_telegram_bot.lock", kill_existing=True):
        self.lock_file = lock_file
        self.kill_existing = kill_existing
        self.lock_fd = None

    def _terminate_process(self, pid):
        """Terminate a process gracefully, then forcefully if needed."""
        try:
            proc = psutil.Process(pid)
            logger.info(f"Terminating existing bot process with PID: {pid}")
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except psutil.TimeoutExpired:
                logger.warning(f"Process {pid} did not terminate in time. Killing it forcefully.")
                proc.kill()
        except psutil.NoSuchProcess:
            logger.debug(f"Process {pid} no longer exists.")
        except Exception as e:
            logger.error(f"Error terminating process {pid}: {e}")

    def _check_and_kill_existing(self):
        """Check the lock file for an existing PID and terminate it."""
        if not os.path.exists(self.lock_file):
            return

        try:
            with open(self.lock_file, 'r') as f:
                pid_str = f.read().strip()
                if pid_str.isdigit():
                    pid = int(pid_str)
                    if psutil.pid_exists(pid):
                        self._terminate_process(pid)
        except Exception as e:
            logger.warning(f"Failed to read lock file or kill existing process: {e}")

    def acquire_lock(self):
        """Acquire an exclusive file lock to ensure single instance."""
        if self.kill_existing:
            self._check_and_kill_existing()

        self.lock_fd = open(self.lock_file, 'w')
        try:
            # Acquire a non-blocking exclusive lock
            fcntl.lockf(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except IOError:
            logger.error(f"Conflict: Another instance is already running and holds the lock {self.lock_file}.")
            sys.exit(1)
        
        # Write current PID to the lock file
        self.lock_fd.write(str(os.getpid()))
        self.lock_fd.flush()
        logger.info(f"Acquired single-instance lock for Telegram bot (PID: {os.getpid()}).")

    def release_lock(self):
        """Release the file lock and clean up."""
        if self.lock_fd:
            try:
                fcntl.lockf(self.lock_fd, fcntl.LOCK_UN)
                self.lock_fd.close()
                if os.path.exists(self.lock_file):
                    os.remove(self.lock_file)
                logger.info("Released single-instance lock.")
            except Exception as e:
                logger.warning(f"Error releasing lock: {e}")

    def __enter__(self):
        self.acquire_lock()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release_lock()

def single_instance_bot(lock_file="/tmp/jarvis_telegram_bot.lock"):
    """
    Decorator to ensure that the Telegram bot polling function runs as a single instance.
    
    Usage:
        @single_instance_bot()
        def start_bot():
            updater.start_polling()
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            with BotInstanceManager(lock_file=lock_file, kill_existing=True):
                return func(*args, **kwargs)
        return wrapper
    return decorator

def get_running_services(service_name_pattern):
    """
    Get a list of running processes matching the service name pattern.
    """
    services = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info.get('cmdline') or []
            if any(service_name_pattern in cmd for cmd in cmdline):
                services.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return services

def restart_service(service_name):
    """
    Restart a systemd service or a known background process.
    """
    try:
        logger.info(f"Attempting to restart service: {service_name}")
        subprocess.run(["sudo", "systemctl", "restart", service_name], check=True)
        logger.info(f"Successfully restarted {service_name}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to restart service {service_name}: {e}")
        return False
    except FileNotFoundError:
        logger.warning("systemctl not found. Ensure you are on a systemd-based Linux distribution.")
        return False

def kill_duplicate_processes(process_name, exclude_pid=None):
    """
    Kill all processes matching the process_name, except the exclude_pid.
    Useful for cleaning up zombie or duplicate bot instances manually.
    """
    if exclude_pid is None:
        exclude_pid = os.getpid()
        
    killed_count = 0
    for proc in get_running_services(process_name):
        if proc.pid == exclude_pid:
            continue
        try:
            logger.info(f"Terminating duplicate process {proc.pid} matching '{process_name}'")
            proc.terminate()
            proc.wait(timeout=3)
            killed_count += 1
        except psutil.TimeoutExpired:
            logger.warning(f"Process {proc.pid} did not terminate gracefully. Killing forcefully.")
            proc.kill()
            killed_count += 1
        except Exception as e:
            logger.error(f"Error terminating process {proc.pid}: {e}")
            
    return killed_count
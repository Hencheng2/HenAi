#!/usr/bin/env python3
"""
Full-featured Terminal Emulator for HenAi
Supports Windows, Linux, and macOS with real system command execution
Can be imported and used within Flask applications
"""

import os
import sys
import subprocess
import shutil
import signal
import threading
import queue
import time
import platform
import re
import glob
import stat
import hashlib
import tempfile
import zipfile
import tarfile
import json
import csv
import pickle
import sqlite3
import argparse
import logging
import configparser
import urllib.request
import urllib.parse
import socket
import psutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict, Any, Callable, Union
from dataclasses import dataclass, field
from enum import Enum
import warnings

# Platform detection
IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"
IS_MAC = platform.system() == "Darwin"

# ANSI color codes for cross-platform colored output
class Colors:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    UNDERLINE = '\033[4m'
    BLINK = '\033[5m'
    REVERSE = '\033[7m'
    HIDDEN = '\033[8m'
    
    # Foreground colors
    BLACK = '\033[30m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    GRAY = '\033[90m'
    
    # Background colors
    BG_BLACK = '\033[40m'
    BG_RED = '\033[101m'
    BG_GREEN = '\033[102m'
    BG_YELLOW = '\033[103m'
    BG_BLUE = '\033[104m'
    BG_MAGENTA = '\033[105m'
    BG_CYAN = '\033[106m'
    BG_WHITE = '\033[107m'
    
    @staticmethod
    def disable():
        """Disable colored output for Windows compatibility"""
        if IS_WINDOWS:
            return True
        return False


class CommandType(Enum):
    BUILTIN = "builtin"
    SYSTEM = "system"
    ALIAS = "alias"
    FUNCTION = "function"


@dataclass
class CommandResult:
    """Result of command execution"""
    success: bool
    output: str
    error: str = ""
    exit_code: int = 0
    execution_time: float = 0.0
    command: str = ""


@dataclass
class ProcessInfo:
    """Information about a running process"""
    pid: int
    name: str
    status: str
    cpu_percent: float
    memory_percent: float
    memory_rss: int
    memory_vms: int
    create_time: float
    username: str
    cmdline: List[str]
    parent_pid: Optional[int] = None


class HistoryManager:
    """Manages command history with persistence"""
    
    def __init__(self, history_file: str = None):
        if not history_file:
            history_file = os.path.expanduser("~/.terminal_history")
        self.history_file = history_file
        self.history: List[str] = []
        self.current_index: int = -1
        self.load_history()
    
    def load_history(self):
        """Load command history from file"""
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self.history = [line.strip() for line in f if line.strip()]
        except Exception:
            self.history = []
        self.current_index = len(self.history)
    
    def save_history(self):
        """Save command history to file"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                for cmd in self.history[-1000:]:  # Keep last 1000 commands
                    f.write(cmd + '\n')
        except Exception:
            pass
    
    def add_command(self, command: str):
        """Add command to history"""
        if not command or command.strip() == "":
            return
        if self.history and self.history[-1] == command:
            return
        self.history.append(command)
        self.current_index = len(self.history)
        self.save_history()
    
    def get_previous(self) -> Optional[str]:
        """Get previous command in history"""
        if self.current_index > 0:
            self.current_index -= 1
            return self.history[self.current_index]
        return None
    
    def get_next(self) -> Optional[str]:
        """Get next command in history"""
        if self.current_index < len(self.history) - 1:
            self.current_index += 1
            return self.history[self.current_index]
        self.current_index = len(self.history)
        return None
    
    def search(self, pattern: str) -> List[str]:
        """Search history for commands matching pattern"""
        return [cmd for cmd in self.history if pattern in cmd]
    
    def clear(self):
        """Clear command history"""
        self.history = []
        self.current_index = 0
        self.save_history()


class AliasManager:
    """Manages command aliases"""
    
    def __init__(self, alias_file: str = None):
        if not alias_file:
            alias_file = os.path.expanduser("~/.terminal_aliases")
        self.alias_file = alias_file
        self.aliases: Dict[str, str] = {}
        self.load_aliases()
    
    def load_aliases(self):
        """Load aliases from file"""
        try:
            if os.path.exists(self.alias_file):
                with open(self.alias_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and '=' in line and not line.startswith('#'):
                            name, cmd = line.split('=', 1)
                            self.aliases[name.strip()] = cmd.strip()
        except Exception:
            pass
    
    def save_aliases(self):
        """Save aliases to file"""
        try:
            with open(self.alias_file, 'w', encoding='utf-8') as f:
                for name, cmd in self.aliases.items():
                    f.write(f"{name}={cmd}\n")
        except Exception:
            pass
    
    def add_alias(self, name: str, command: str) -> bool:
        """Add or update an alias"""
        if not name or not re.match(r'^[a-zA-Z0-9_\-]+$', name):
            return False
        self.aliases[name] = command
        self.save_aliases()
        return True
    
    def remove_alias(self, name: str) -> bool:
        """Remove an alias"""
        if name in self.aliases:
            del self.aliases[name]
            self.save_aliases()
            return True
        return False
    
    def get_alias(self, name: str) -> Optional[str]:
        """Get alias command"""
        return self.aliases.get(name)
    
    def expand(self, command: str) -> str:
        """Expand aliases in command"""
        parts = command.split()
        if not parts:
            return command
        if parts[0] in self.aliases:
            return self.aliases[parts[0]] + ' ' + ' '.join(parts[1:])
        return command
    
    def list_aliases(self) -> Dict[str, str]:
        """List all aliases"""
        return self.aliases.copy()


class EnvironmentManager:
    """Manages environment variables"""
    
    def __init__(self):
        self.env = os.environ.copy()
        self.custom_vars: Dict[str, str] = {}
    
    def get(self, key: str, default: str = None) -> Optional[str]:
        """Get environment variable"""
        if key in self.custom_vars:
            return self.custom_vars[key]
        return self.env.get(key, default)
    
    def set(self, key: str, value: str, permanent: bool = False):
        """Set environment variable"""
        if permanent:
            self.custom_vars[key] = value
        else:
            self.env[key] = value
    
    def unset(self, key: str):
        """Unset environment variable"""
        if key in self.custom_vars:
            del self.custom_vars[key]
        if key in self.env:
            del self.env[key]
    
    def get_all(self) -> Dict[str, str]:
        """Get all environment variables"""
        result = self.env.copy()
        result.update(self.custom_vars)
        return result
    
    def expand(self, value: str) -> str:
        """Expand environment variables in string"""
        return os.path.expandvars(value)


class VirtualEnvironmentManager:
    """Manages Python virtual environments"""
    
    def __init__(self, terminal):
        self.terminal = terminal
        self.current_venv: Optional[str] = None
        self.current_venv_path: Optional[str] = None
        self.venv_python_path: Optional[str] = None
        self.venv_pip_path: Optional[str] = None
    
    def create_venv(self, name: str, path: str = None, python_version: str = None) -> CommandResult:
        """Create a new virtual environment"""
        if not path:
            path = os.getcwd()
        
        venv_path = os.path.join(path, name)
        
        if os.path.exists(venv_path):
            return CommandResult(
                success=False,
                output="",
                error=f"Virtual environment '{name}' already exists at {venv_path}",
                exit_code=1,
                command=f"venv create {name}"
            )
        
        try:
            python_cmd = sys.executable
            if python_version:
                # Try to use specified Python version
                python_cmd = f"python{python_version}"
            
            result = subprocess.run(
                [python_cmd, "-m", "venv", venv_path],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                return CommandResult(
                    success=True,
                    output=f"Virtual environment '{name}' created successfully at {venv_path}\n\nTo activate: venv activate {name}",
                    exit_code=0,
                    command=f"venv create {name}"
                )
            else:
                return CommandResult(
                    success=False,
                    output="",
                    error=result.stderr,
                    exit_code=result.returncode,
                    command=f"venv create {name}"
                )
                
        except subprocess.TimeoutExpired:
            return CommandResult(
                success=False,
                output="",
                error="Operation timed out",
                exit_code=1,
                command=f"venv create {name}"
            )
        except Exception as e:
            return CommandResult(
                success=False,
                output="",
                error=str(e),
                exit_code=1,
                command=f"venv create {name}"
            )
    
    def activate_venv(self, name: str, path: str = None) -> CommandResult:
        """Activate a virtual environment"""
        if not path:
            path = os.getcwd()
        
        venv_path = os.path.join(path, name)
        
        if not os.path.exists(venv_path):
            return CommandResult(
                success=False,
                output="",
                error=f"Virtual environment '{name}' not found at {venv_path}",
                exit_code=1,
                command=f"venv activate {name}"
            )
        
        if IS_WINDOWS:
            python_path = os.path.join(venv_path, "Scripts", "python.exe")
            pip_path = os.path.join(venv_path, "Scripts", "pip.exe")
            activate_script = os.path.join(venv_path, "Scripts", "activate")
        else:
            python_path = os.path.join(venv_path, "bin", "python")
            pip_path = os.path.join(venv_path, "bin", "pip")
            activate_script = os.path.join(venv_path, "bin", "activate")
        
        if os.path.exists(python_path):
            self.current_venv = name
            self.current_venv_path = venv_path
            self.venv_python_path = python_path
            self.venv_pip_path = pip_path
            
            output = f"Activated virtual environment: {name}\n"
            output += f"Python: {python_path}\n"
            output += f"Pip: {pip_path}\n\n"
            output += f"Run 'deactivate' to exit this environment."
            
            return CommandResult(
                success=True,
                output=output,
                exit_code=0,
                command=f"venv activate {name}"
            )
        else:
            return CommandResult(
                success=False,
                output="",
                error=f"Python executable not found in virtual environment",
                exit_code=1,
                command=f"venv activate {name}"
            )
    
    def deactivate_venv(self) -> CommandResult:
        """Deactivate current virtual environment"""
        if not self.current_venv:
            return CommandResult(
                success=False,
                output="",
                error="No virtual environment is currently active",
                exit_code=1,
                command="venv deactivate"
            )
        
        output = f"Deactivated virtual environment: {self.current_venv}"
        self.current_venv = None
        self.current_venv_path = None
        self.venv_python_path = None
        self.venv_pip_path = None
        
        return CommandResult(
            success=True,
            output=output,
            exit_code=0,
            command="venv deactivate"
        )
    
    def list_venvs(self, path: str = None) -> CommandResult:
        """List all virtual environments in current directory"""
        if not path:
            path = os.getcwd()
        
        venvs = []
        try:
            for item in os.listdir(path):
                item_path = os.path.join(path, item)
                if os.path.isdir(item_path):
                    if IS_WINDOWS:
                        check_path = os.path.join(item_path, "Scripts", "python.exe")
                    else:
                        check_path = os.path.join(item_path, "bin", "python")
                    
                    if os.path.exists(check_path):
                        venvs.append(item)
        except PermissionError:
            pass
        
        output = "Virtual environments found:\n"
        for venv in venvs:
            indicator = " [ACTIVE]" if venv == self.current_venv else ""
            output += f"  - {venv}{indicator}\n"
        
        if not venvs:
            output = "No virtual environments found in current directory"
        
        return CommandResult(
            success=True,
            output=output,
            exit_code=0,
            command="venv list"
        )
    
    def install_package(self, package: str, version: str = None) -> CommandResult:
        """Install a package in the active virtual environment"""
        if not self.current_venv:
            return CommandResult(
                success=False,
                output="",
                error="No virtual environment is active. Use 'venv activate <name>' first.",
                exit_code=1,
                command=f"pip install {package}"
            )
        
        pkg_spec = f"{package}=={version}" if version else package
        
        try:
            result = subprocess.run(
                [self.venv_python_path, "-m", "pip", "install", pkg_spec],
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0:
                return CommandResult(
                    success=True,
                    output=result.stdout,
                    exit_code=0,
                    command=f"pip install {package}"
                )
            else:
                return CommandResult(
                    success=False,
                    output="",
                    error=result.stderr,
                    exit_code=result.returncode,
                    command=f"pip install {package}"
                )
                
        except subprocess.TimeoutExpired:
            return CommandResult(
                success=False,
                output="",
                error="Installation timed out",
                exit_code=1,
                command=f"pip install {package}"
            )
        except Exception as e:
            return CommandResult(
                success=False,
                output="",
                error=str(e),
                exit_code=1,
                command=f"pip install {package}"
            )
    
    def uninstall_package(self, package: str) -> CommandResult:
        """Uninstall a package from the active virtual environment"""
        if not self.current_venv:
            return CommandResult(
                success=False,
                output="",
                error="No virtual environment is active",
                exit_code=1,
                command=f"pip uninstall {package}"
            )
        
        try:
            result = subprocess.run(
                [self.venv_python_path, "-m", "pip", "uninstall", package, "-y"],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                return CommandResult(
                    success=True,
                    output=result.stdout,
                    exit_code=0,
                    command=f"pip uninstall {package}"
                )
            else:
                return CommandResult(
                    success=False,
                    output="",
                    error=result.stderr,
                    exit_code=result.returncode,
                    command=f"pip uninstall {package}"
                )
        except Exception as e:
            return CommandResult(
                success=False,
                output="",
                error=str(e),
                exit_code=1,
                command=f"pip uninstall {package}"
            )
    
    def list_packages(self) -> CommandResult:
        """List installed packages in active virtual environment"""
        if not self.current_venv:
            return CommandResult(
                success=False,
                output="",
                error="No virtual environment is active",
                exit_code=1,
                command="pip list"
            )
        
        try:
            result = subprocess.run(
                [self.venv_python_path, "-m", "pip", "list"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            return CommandResult(
                success=result.returncode == 0,
                output=result.stdout,
                error=result.stderr if result.returncode != 0 else "",
                exit_code=result.returncode,
                command="pip list"
            )
        except Exception as e:
            return CommandResult(
                success=False,
                output="",
                error=str(e),
                exit_code=1,
                command="pip list"
            )
    
    def freeze_requirements(self, output_file: str = "requirements.txt") -> CommandResult:
        """Generate requirements.txt from active virtual environment"""
        if not self.current_venv:
            return CommandResult(
                success=False,
                output="",
                error="No virtual environment is active",
                exit_code=1,
                command=f"pip freeze > {output_file}"
            )
        
        try:
            result = subprocess.run(
                [self.venv_python_path, "-m", "pip", "freeze"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(result.stdout)
                return CommandResult(
                    success=True,
                    output=f"Requirements saved to {output_file}\n\n{result.stdout[:500]}{'...' if len(result.stdout) > 500 else ''}",
                    exit_code=0,
                    command=f"pip freeze > {output_file}"
                )
            else:
                return CommandResult(
                    success=False,
                    output="",
                    error=result.stderr,
                    exit_code=result.returncode,
                    command=f"pip freeze > {output_file}"
                )
        except Exception as e:
            return CommandResult(
                success=False,
                output="",
                error=str(e),
                exit_code=1,
                command=f"pip freeze > {output_file}"
            )
    
    def install_requirements(self, requirements_file: str = "requirements.txt") -> CommandResult:
        """Install packages from requirements.txt"""
        if not self.current_venv:
            return CommandResult(
                success=False,
                output="",
                error="No virtual environment is active",
                exit_code=1,
                command=f"pip install -r {requirements_file}"
            )
        
        try:
            result = subprocess.run(
                [self.venv_python_path, "-m", "pip", "install", "-r", requirements_file],
                capture_output=True,
                text=True,
                timeout=300
            )
            
            return CommandResult(
                success=result.returncode == 0,
                output=result.stdout,
                error=result.stderr if result.returncode != 0 else "",
                exit_code=result.returncode,
                command=f"pip install -r {requirements_file}"
            )
        except subprocess.TimeoutExpired:
            return CommandResult(
                success=False,
                output="",
                error="Installation timed out",
                exit_code=1,
                command=f"pip install -r {requirements_file}"
            )
        except Exception as e:
            return CommandResult(
                success=False,
                output="",
                error=str(e),
                exit_code=1,
                command=f"pip install -r {requirements_file}"
            )
    
    def run_in_venv(self, command: List[str]) -> subprocess.Popen:
        """Run a command in the active virtual environment"""
        if self.current_venv:
            # Prepend venv python path if command starts with python
            if command and command[0] in ['python', 'python3']:
                command = [self.venv_python_path] + command[1:]
        return subprocess.Popen(command, shell=IS_WINDOWS)
    
    def get_venv_info(self) -> Dict[str, Any]:
        """Get information about current virtual environment"""
        if not self.current_venv:
            return {"active": False}
        
        return {
            "active": True,
            "name": self.current_venv,
            "path": self.current_venv_path,
            "python": self.venv_python_path,
            "pip": self.venv_pip_path
        }


class FileSystemManager:
    """Manages file system operations"""
    
    def __init__(self, terminal):
        self.terminal = terminal
    
    def ls(self, args: List[str]) -> CommandResult:
        """List directory contents with PowerShell-style table format - workspace only"""
        try:
            workspace_root = getattr(self.terminal, 'workspace_root', os.path.abspath('.'))
            path = self.terminal.current_directory
            
            # Ensure path is within workspace
            try:
                if not path.startswith(workspace_root):
                    path = workspace_root
                    self.terminal.current_directory = workspace_root
            except (ValueError, AttributeError):
                path = workspace_root
                self.terminal.current_directory = workspace_root
            
            show_all = False
            long_format = False
            human_readable = False
            recursive = False
            
            for arg in args:
                if arg == '-a' or arg == '--all':
                    show_all = True
                elif arg == '-l':
                    long_format = True
                elif arg == '-h' or arg == '--human-readable':
                    human_readable = True
                elif arg == '-R' or arg == '--recursive':
                    recursive = True
                elif not arg.startswith('-'):
                    # Handle relative paths within workspace
                    target = arg
                    # Remove any Windows drive letters
                    target = re.sub(r'^[A-Za-z]:\\', '', target)
                    target = target.replace('/', os.sep).replace('\\', os.sep)
                    if os.path.isabs(target):
                        target = os.path.normpath(target)
                    else:
                        target = os.path.join(self.terminal.current_directory, target)
                    # Ensure within workspace
                    try:
                        if target.startswith(workspace_root):
                            path = target
                        else:
                            return CommandResult(
                                success=False,
                                output="",
                                error=f"Cannot access outside workspace: {arg}",
                                exit_code=1,
                                command=f"ls {' '.join(args)}"
                            )
                    except (ValueError, AttributeError):
                        path = workspace_root
            
            if not os.path.exists(path):
                return CommandResult(
                    success=False,
                    output="",
                    error=f"Path not found: {path}",
                    exit_code=1,
                    command=f"ls {' '.join(args)}"
                )
            
            if recursive:
                return self._ls_recursive(path, show_all, long_format, human_readable)
            
            items = os.listdir(path)
            
            if not show_all:
                items = [item for item in items if not item.startswith('.')]
            
            items.sort()
            
            # Always use table format (PowerShell style)
            output = self._format_powershell_table(path, items)
            
            return CommandResult(
                success=True,
                output=output,
                exit_code=0,
                command=f"ls {' '.join(args)}"
            )
            
        except PermissionError:
            return CommandResult(
                success=False,
                output="",
                error="Permission denied",
                exit_code=1,
                command=f"ls {' '.join(args)}"
            )
        except Exception as e:
            return CommandResult(
                success=False,
                output="",
                error=str(e),
                exit_code=1,
                command=f"ls {' '.join(args)}"
            )
            
            for arg in args:
                if arg == '-a' or arg == '--all':
                    show_all = True
                elif arg == '-l':
                    long_format = True
                elif arg == '-h' or arg == '--human-readable':
                    human_readable = True
                elif arg == '-R' or arg == '--recursive':
                    recursive = True
                elif not arg.startswith('-'):
                    path = os.path.join(self.terminal.current_directory, arg)
            
            if not os.path.exists(path):
                return CommandResult(
                    success=False,
                    output="",
                    error=f"Path not found: {path}",
                    exit_code=1,
                    command=f"ls {' '.join(args)}"
                )
            
            if recursive:
                return self._ls_recursive(path, show_all, long_format, human_readable)
            
            items = os.listdir(path)
            
            if not show_all:
                items = [item for item in items if not item.startswith('.')]
            
            items.sort()
            
            # Always use table format (PowerShell style)
            output = self._format_powershell_table(path, items)
            
            return CommandResult(
                success=True,
                output=output,
                exit_code=0,
                command=f"ls {' '.join(args)}"
            )
            
        except PermissionError:
            return CommandResult(
                success=False,
                output="",
                error="Permission denied",
                exit_code=1,
                command=f"ls {' '.join(args)}"
            )
        except Exception as e:
            return CommandResult(
                success=False,
                output="",
                error=str(e),
                exit_code=1,
                command=f"ls {' '.join(args)}"
            )
    
    def _format_powershell_table(self, path: str, items: List[str]) -> str:
        """Format directory listing as PowerShell-style table"""
        if not items:
            return "Directory is empty."
        
        # Collect file information
        file_infos = []
        max_name_len = 4  # "Name" minimum
        max_mode_len = 6  # "Mode" minimum
        max_size_len = 6   # "Length" minimum
        
        for item in items:
            item_path = os.path.join(path, item)
            try:
                stat_info = os.stat(item_path)
                is_dir = os.path.isdir(item_path)
                is_symlink = os.path.islink(item_path)
                
                # Mode string (d----- for directory, -a---- for file)
                if is_dir:
                    mode = "d-----"
                elif is_symlink:
                    mode = "l-----"
                else:
                    # Check if executable
                    is_exec = os.access(item_path, os.X_OK)
                    mode = "-a----" if is_exec else "------"
                
                # Size
                size = stat_info.st_size
                size_str = f"{size:,}" if size > 0 else "0"
                
                # Last write time
                mtime = datetime.fromtimestamp(stat_info.st_mtime)
                time_str = mtime.strftime("%m/%d/%Y %I:%M %p").lstrip('0').replace(' 0', ' ')
                
                name = item + ("/" if is_dir else "")
                
                file_infos.append({
                    'mode': mode,
                    'size': size_str,
                    'size_bytes': size,
                    'time': time_str,
                    'name': name,
                    'is_dir': is_dir
                })
                
                max_name_len = max(max_name_len, len(name))
                max_mode_len = max(max_mode_len, len(mode))
                max_size_len = max(max_size_len, len(size_str))
                
            except (PermissionError, OSError):
                file_infos.append({
                    'mode': "?-----",
                    'size': "?",
                    'size_bytes': 0,
                    'time': "?",
                    'name': item,
                    'is_dir': False
                })
        
        # Build the table header
        separator = "-" * (max_mode_len + max_size_len + max_name_len + 20)
        
        output = []
        output.append("")
        output.append(f"    Directory: {self._get_friendly_path(path)}")
        output.append("")
        output.append(f"{'Mode':<{max_mode_len}} {'LastWriteTime':<20} {'Length':<{max_size_len}} Name")
        output.append(f"{'-' * max_mode_len:<{max_mode_len}} {'-' * 20:<20} {'-' * max_size_len:<{max_size_len}} {'-' * max_name_len}")
        
        # Sort: directories first, then files
        file_infos.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
        
        for info in file_infos:
            output.append(f"{info['mode']:<{max_mode_len}} {info['time']:<20} {info['size']:>{max_size_len}} {info['name']}")
        
        return '\n'.join(output)
    
    def _get_friendly_path(self, path: str) -> str:
        """Convert system path to friendly HenAi path format - workspace only"""
        # Force everything to be relative to workspace root
        workspace_root = getattr(self.terminal, 'workspace_root', os.path.abspath('.'))
        
        try:
            # Get path relative to workspace root
            rel_path = os.path.relpath(path, workspace_root)
            
            # Handle special cases
            if rel_path == '.':
                return "HenAi:\\Workspace"
            elif rel_path.startswith('..'):
                # This should never happen - we shouldn't allow navigation outside workspace
                # But if it does, just show as Workspace
                return "HenAi:\\Workspace"
            else:
                # Convert to Windows-style path for display
                display_path = rel_path.replace('/', '\\')
                return f"HenAi:\\Workspace\\{display_path}"
        except ValueError:
            # If paths are on different drives, just show Workspace
            return "HenAi:\\Workspace"
    
    def _ls_recursive(self, path: str, show_all: bool, long_format: bool, human_readable: bool) -> CommandResult:
        """Recursive directory listing"""
        output = []
        
        def walk_dir(current_path: str, indent: str = ""):
            try:
                items = os.listdir(current_path)
                if not show_all:
                    items = [item for item in items if not item.startswith('.')]
                items.sort()
                
                rel_path = os.path.relpath(current_path, path)
                if rel_path == '.':
                    output.append(f"\n{current_path}:")
                else:
                    output.append(f"\n{current_path}:")
                
                for item in items:
                    item_path = os.path.join(current_path, item)
                    if long_format:
                        output.append(self._get_file_info_line(item_path, human_readable))
                    else:
                        if os.path.isdir(item_path):
                            output.append(f"{Colors.BLUE}{item}/{Colors.RESET}")
                        elif os.access(item_path, os.X_OK):
                            output.append(f"{Colors.GREEN}{item}{Colors.RESET}")
                        else:
                            output.append(item)
                
                for item in items:
                    item_path = os.path.join(current_path, item)
                    if os.path.isdir(item_path):
                        walk_dir(item_path, indent + "  ")
                        
            except PermissionError:
                output.append(f"{indent}[Permission Denied]")
            except Exception:
                pass
        
        walk_dir(path)
        return CommandResult(
            success=True,
            output='\n'.join(output),
            exit_code=0,
            command="ls -R"
        )
    
    def _format_short_listing(self, path: str, items: List[str]) -> str:
        """Format short directory listing"""
        columns = 4
        col_width = max(len(item) for item in items) + 2 if items else 10
        rows = (len(items) + columns - 1) // columns
        
        output_lines = []
        for row in range(rows):
            line = ""
            for col in range(columns):
                idx = row + col * rows
                if idx < len(items):
                    item = items[idx]
                    item_path = os.path.join(path, item)
                    if os.path.isdir(item_path):
                        line += f"{Colors.BLUE}{item}{Colors.RESET}".ljust(col_width)
                    elif os.access(item_path, os.X_OK):
                        line += f"{Colors.GREEN}{item}{Colors.RESET}".ljust(col_width)
                    else:
                        line += item.ljust(col_width)
            output_lines.append(line.rstrip())
        
        return '\n'.join(output_lines)
    
    def _format_long_listing(self, path: str, items: List[str], human_readable: bool) -> str:
        """Format long directory listing (like ls -l)"""
        output = []
        
        for item in items:
            item_path = os.path.join(path, item)
            output.append(self._get_file_info_line(item_path, human_readable))
        
        return '\n'.join(output)
    
    def _get_file_info_line(self, file_path: str, human_readable: bool) -> str:
        """Get detailed file information line"""
        try:
            stat_info = os.stat(file_path)
            
            # File type and permissions
            mode = stat_info.st_mode
            file_type = 'd' if os.path.isdir(file_path) else '-'
            perms = ''
            for i, who in enumerate([stat.S_IRUSR, stat.S_IWUSR, stat.S_IXUSR,
                                      stat.S_IRGRP, stat.S_IWGRP, stat.S_IXGRP,
                                      stat.S_IROTH, stat.S_IWOTH, stat.S_IXOTH]):
                perms += 'r' if mode & who and i % 3 == 0 else ''
                perms += 'w' if mode & who and i % 3 == 1 else ''
                perms += 'x' if mode & who and i % 3 == 2 else '-'
            
            # Number of hard links
            nlink = stat_info.st_nlink
            
            # Owner and group
            try:
                import pwd, grp
                owner = pwd.getpwuid(stat_info.st_uid).pw_name
                group = grp.getgrgid(stat_info.st_gid).gr_name
            except:
                owner = str(stat_info.st_uid)
                group = str(stat_info.st_gid)
            
            # Size
            size = stat_info.st_size
            if human_readable:
                size = self._human_readable_size(size)
            else:
                size = str(size)
            
            # Modification time
            mtime = datetime.fromtimestamp(stat_info.st_mtime).strftime("%b %d %H:%M")
            
            # Name
            name = os.path.basename(file_path)
            if os.path.isdir(file_path):
                name = f"{Colors.BLUE}{name}/{Colors.RESET}"
            elif os.access(file_path, os.X_OK):
                name = f"{Colors.GREEN}{name}{Colors.RESET}"
            
            return f"{file_type}{perms} {nlink:2} {owner} {group} {size:>8} {mtime} {name}"
            
        except Exception:
            return f"[Error] {os.path.basename(file_path)}"
    
    def _human_readable_size(self, size: int) -> str:
        """Convert size to human readable format"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.1f}{unit}"
            size /= 1024.0
        return f"{size:.1f}PB"
    
    def cd(self, args: List[str]) -> CommandResult:
        """Change directory - STRICTLY within workspace only"""
        workspace_root = getattr(self.terminal, 'workspace_root', os.path.abspath('.'))
        
        if not args:
            # Go to workspace root
            new_dir = workspace_root
        else:
            new_dir = args[0]
            
            # Handle special paths
            if new_dir == '~' or new_dir == '~\\' or new_dir == '/' or new_dir == '\\':
                new_dir = workspace_root
            elif new_dir == '..':
                # Go up one level, but never above workspace root
                current = self.terminal.current_directory
                parent = os.path.dirname(current)
                if os.path.commonpath([parent, workspace_root]) == workspace_root:
                    new_dir = parent
                else:
                    new_dir = workspace_root
            else:
                # Remove any Windows drive letters or backslashes
                new_dir = new_dir.replace('C:\\', '').replace('D:\\', '').replace(':\\', '')
                new_dir = new_dir.replace('/', os.sep).replace('\\', os.sep)
                
                # Build absolute path within workspace
                if os.path.isabs(new_dir):
                    # If it's absolute, make it relative to workspace root
                    new_dir = os.path.normpath(new_dir)
                else:
                    new_dir = os.path.join(self.terminal.current_directory, new_dir)
        
        new_dir = os.path.normpath(new_dir)
        
        # CRITICAL: Never allow navigation outside workspace root
        try:
            if not new_dir.startswith(workspace_root):
                new_dir = workspace_root
        except (ValueError, AttributeError):
            new_dir = workspace_root
        
        if os.path.exists(new_dir) and os.path.isdir(new_dir):
            self.terminal.current_directory = new_dir
            os.chdir(new_dir)
            friendly_path = self._get_friendly_path(new_dir)
            return CommandResult(
                success=True,
                output=friendly_path,
                exit_code=0,
                command=f"cd {' '.join(args)}"
            )
        else:
            return CommandResult(
                success=False,
                output="",
                error=f"Directory not found: {new_dir}",
                exit_code=1,
                command=f"cd {' '.join(args)}"
            )
    
    def pwd(self, args: List[str]) -> CommandResult:
        """Print working directory (friendly format)"""
        friendly_path = self._get_friendly_path(self.terminal.current_directory)
        return CommandResult(
            success=True,
            output=friendly_path,
            exit_code=0,
            command="pwd"
        )
    
    def mkdir(self, args: List[str]) -> CommandResult:
        """Create directories"""
        if not args:
            return CommandResult(
                success=False,
                output="",
                error="Usage: mkdir [-p] <directory>...",
                exit_code=1,
                command="mkdir"
            )
        
        parents = '-p' in args or '--parents' in args
        args = [arg for arg in args if not arg.startswith('-')]
        
        output = []
        errors = []
        
        for dirname in args:
            try:
                dirpath = os.path.join(self.terminal.current_directory, dirname)
                if parents:
                    os.makedirs(dirpath, exist_ok=True)
                else:
                    os.mkdir(dirpath)
                output.append(f"Created directory: {dirname}")
            except FileExistsError:
                errors.append(f"Directory already exists: {dirname}")
            except Exception as e:
                errors.append(f"Failed to create {dirname}: {str(e)}")
        
        return CommandResult(
            success=len(errors) == 0,
            output='\n'.join(output),
            error='\n'.join(errors) if errors else "",
            exit_code=0 if not errors else 1,
            command=f"mkdir {' '.join(args)}"
        )
    
    def rmdir(self, args: List[str]) -> CommandResult:
        """Remove empty directories"""
        if not args:
            return CommandResult(
                success=False,
                output="",
                error="Usage: rmdir <directory>...",
                exit_code=1,
                command="rmdir"
            )
        
        output = []
        errors = []
        
        for dirname in args:
            try:
                os.rmdir(os.path.join(self.terminal.current_directory, dirname))
                output.append(f"Removed directory: {dirname}")
            except OSError as e:
                errors.append(f"Failed to remove {dirname}: {str(e)}")
        
        return CommandResult(
            success=len(errors) == 0,
            output='\n'.join(output),
            error='\n'.join(errors) if errors else "",
            exit_code=0 if not errors else 1,
            command=f"rmdir {' '.join(args)}"
        )
    
    def rm(self, args: List[str]) -> CommandResult:
        """Remove files or directories"""
        if not args:
            return CommandResult(
                success=False,
                output="",
                error="Usage: rm [-r] [-f] <file>...",
                exit_code=1,
                command="rm"
            )
        
        recursive = '-r' in args or '-rf' in args
        force = '-f' in args or '-rf' in args
        args = [arg for arg in args if not arg.startswith('-')]
        
        output = []
        errors = []
        
        for filename in args:
            try:
                path = os.path.join(self.terminal.current_directory, filename)
                if os.path.isdir(path):
                    if recursive:
                        shutil.rmtree(path)
                        output.append(f"Removed directory: {filename}")
                    else:
                        errors.append(f"Cannot remove directory '{filename}'. Use -r flag")
                else:
                    os.remove(path)
                    output.append(f"Removed file: {filename}")
            except FileNotFoundError:
                if not force:
                    errors.append(f"File not found: {filename}")
            except Exception as e:
                if not force:
                    errors.append(f"Failed to remove {filename}: {str(e)}")
        
        return CommandResult(
            success=len(errors) == 0,
            output='\n'.join(output),
            error='\n'.join(errors) if errors else "",
            exit_code=0 if not errors else 1,
            command=f"rm {' '.join(args)}"
        )
    
    def cp(self, args: List[str]) -> CommandResult:
        """Copy files or directories"""
        if len(args) < 2:
            return CommandResult(
                success=False,
                output="",
                error="Usage: cp [-r] <source> <destination>",
                exit_code=1,
                command="cp"
            )
        
        recursive = '-r' in args
        args = [arg for arg in args if not arg.startswith('-')]
        
        if len(args) < 2:
            return CommandResult(
                success=False,
                output="",
                error="Usage: cp [-r] <source> <destination>",
                exit_code=1,
                command="cp"
            )
        
        src = os.path.join(self.terminal.current_directory, args[0])
        dst = os.path.join(self.terminal.current_directory, args[1])
        
        try:
            if os.path.isdir(src):
                if recursive:
                    shutil.copytree(src, dst)
                else:
                    return CommandResult(
                        success=False,
                        output="",
                        error=f"Source is a directory. Use -r flag to copy directories.",
                        exit_code=1,
                        command=f"cp {' '.join(args)}"
                    )
            else:
                shutil.copy2(src, dst)
            
            return CommandResult(
                success=True,
                output=f"Copied {args[0]} to {args[1]}",
                exit_code=0,
                command=f"cp {' '.join(args)}"
            )
        except Exception as e:
            return CommandResult(
                success=False,
                output="",
                error=str(e),
                exit_code=1,
                command=f"cp {' '.join(args)}"
            )
    
    def mv(self, args: List[str]) -> CommandResult:
        """Move or rename files or directories"""
        if len(args) < 2:
            return CommandResult(
                success=False,
                output="",
                error="Usage: mv <source> <destination>",
                exit_code=1,
                command="mv"
            )
        
        src = os.path.join(self.terminal.current_directory, args[0])
        dst = os.path.join(self.terminal.current_directory, args[1])
        
        try:
            shutil.move(src, dst)
            return CommandResult(
                success=True,
                output=f"Moved {args[0]} to {args[1]}",
                exit_code=0,
                command=f"mv {' '.join(args)}"
            )
        except Exception as e:
            return CommandResult(
                success=False,
                output="",
                error=str(e),
                exit_code=1,
                command=f"mv {' '.join(args)}"
            )
    
    def touch(self, args: List[str]) -> CommandResult:
        """Create empty files or update timestamps"""
        if not args:
            return CommandResult(
                success=False,
                output="",
                error="Usage: touch <file>...",
                exit_code=1,
                command="touch"
            )
        
        output = []
        errors = []
        
        for filename in args:
            try:
                filepath = os.path.join(self.terminal.current_directory, filename)
                with open(filepath, 'a'):
                    os.utime(filepath, None)
                output.append(f"Created/updated: {filename}")
            except Exception as e:
                errors.append(f"Failed: {filename} - {str(e)}")
        
        return CommandResult(
            success=len(errors) == 0,
            output='\n'.join(output),
            error='\n'.join(errors) if errors else "",
            exit_code=0 if not errors else 1,
            command=f"touch {' '.join(args)}"
        )
    
    def cat(self, args: List[str]) -> CommandResult:
        """Concatenate and display files"""
        if not args:
            return CommandResult(
                success=False,
                output="",
                error="Usage: cat <file>...",
                exit_code=1,
                command="cat"
            )
        
        output = []
        errors = []
        
        for filename in args:
            try:
                with open(os.path.join(self.terminal.current_directory, filename), 'r', encoding='utf-8', errors='ignore') as f:
                    output.append(f.read())
            except Exception as e:
                errors.append(f"Failed to read {filename}: {str(e)}")
        
        return CommandResult(
            success=len(errors) == 0,
            output='\n'.join(output),
            error='\n'.join(errors) if errors else "",
            exit_code=0 if not errors else 1,
            command=f"cat {' '.join(args)}"
        )
    
    def head(self, args: List[str]) -> CommandResult:
        """Display first lines of files"""
        n = 10
        if args and args[0].startswith('-n'):
            try:
                n = int(args[0][2:]) if len(args[0]) > 2 else int(args[1])
                args = args[2:] if len(args[0]) == 2 else args[1:]
            except:
                pass
        
        if not args:
            return CommandResult(
                success=False,
                output="",
                error="Usage: head [-n N] <file>",
                exit_code=1,
                command="head"
            )
        
        output = []
        errors = []
        
        for filename in args:
            try:
                with open(os.path.join(self.terminal.current_directory, filename), 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()[:n]
                    output.append(f"==> {filename} <==\n" + ''.join(lines))
            except Exception as e:
                errors.append(f"Failed to read {filename}: {str(e)}")
        
        return CommandResult(
            success=len(errors) == 0,
            output='\n'.join(output),
            error='\n'.join(errors) if errors else "",
            exit_code=0 if not errors else 1,
            command=f"head {' '.join(args)}"
        )
    
    def tail(self, args: List[str]) -> CommandResult:
        """Display last lines of files"""
        n = 10
        if args and args[0].startswith('-n'):
            try:
                n = int(args[0][2:]) if len(args[0]) > 2 else int(args[1])
                args = args[2:] if len(args[0]) == 2 else args[1:]
            except:
                pass
        
        if not args:
            return CommandResult(
                success=False,
                output="",
                error="Usage: tail [-n N] <file>",
                exit_code=1,
                command="tail"
            )
        
        output = []
        errors = []
        
        for filename in args:
            try:
                with open(os.path.join(self.terminal.current_directory, filename), 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()[-n:]
                    output.append(f"==> {filename} <==\n" + ''.join(lines))
            except Exception as e:
                errors.append(f"Failed to read {filename}: {str(e)}")
        
        return CommandResult(
            success=len(errors) == 0,
            output='\n'.join(output),
            error='\n'.join(errors) if errors else "",
            exit_code=0 if not errors else 1,
            command=f"tail {' '.join(args)}"
        )
    
    def find(self, args: List[str]) -> CommandResult:
        """Search for files"""
        search_name = None
        search_type = None
        search_path = self.terminal.current_directory
        
        i = 0
        while i < len(args):
            if args[i] == '-name' and i + 1 < len(args):
                search_name = args[i + 1]
                i += 2
            elif args[i] == '-type' and i + 1 < len(args):
                search_type = args[i + 1]
                i += 2
            elif args[i] == '-path' and i + 1 < len(args):
                search_path = os.path.join(self.terminal.current_directory, args[i + 1])
                i += 2
            else:
                i += 1
        
        if not search_name:
            return CommandResult(
                success=False,
                output="",
                error="Usage: find [-path PATH] -name PATTERN [-type f|d]",
                exit_code=1,
                command="find"
            )
        
        found = []
        pattern = search_name.replace('*', '.*').replace('?', '.')
        
        for root, dirs, files in os.walk(search_path):
            try:
                for name in files + dirs:
                    if re.match(pattern, name, re.IGNORECASE):
                        item_path = os.path.join(root, name)
                        if search_type:
                            if search_type == 'f' and os.path.isfile(item_path):
                                found.append(os.path.relpath(item_path, self.terminal.current_directory))
                            elif search_type == 'd' and os.path.isdir(item_path):
                                found.append(os.path.relpath(item_path, self.terminal.current_directory))
                        else:
                            found.append(os.path.relpath(item_path, self.terminal.current_directory))
            except PermissionError:
                continue
        
        output = '\n'.join(found) if found else f"No files found matching '{search_name}'"
        
        return CommandResult(
            success=True,
            output=output,
            exit_code=0,
            command=f"find {' '.join(args)}"
        )
    
    def grep(self, args: List[str]) -> CommandResult:
        """Search for patterns in files"""
        if len(args) < 2:
            return CommandResult(
                success=False,
                output="",
                error="Usage: grep [-i] PATTERN [FILE]",
                exit_code=1,
                command="grep"
            )
        
        ignore_case = '-i' in args
        args = [arg for arg in args if arg != '-i']
        
        pattern = args[0]
        filename = args[1] if len(args) > 1 else None
        
        if ignore_case:
            pattern = pattern.lower()
        
        if filename:
            try:
                with open(os.path.join(self.terminal.current_directory, filename), 'r', encoding='utf-8', errors='ignore') as f:
                    output = []
                    for line_num, line in enumerate(f, 1):
                        search_line = line.lower() if ignore_case else line
                        if pattern in search_line:
                            output.append(f"{line_num}: {line.rstrip()}")
                    
                    if not output:
                        output = [f"No matches found for '{args[0]}'"]
                    
                    return CommandResult(
                        success=True,
                        output='\n'.join(output),
                        exit_code=0,
                        command=f"grep {' '.join(args)}"
                    )
            except Exception as e:
                return CommandResult(
                    success=False,
                    output="",
                    error=str(e),
                    exit_code=1,
                    command=f"grep {' '.join(args)}"
                )
        else:
            return CommandResult(
                success=False,
                output="",
                error="No file specified",
                exit_code=1,
                command=f"grep {' '.join(args)}"
            )
    
    def tree(self, args: List[str]) -> CommandResult:
        """Display directory tree structure"""
        path = self.terminal.current_directory
        max_depth = None
        show_hidden = False
        
        for arg in args:
            if arg == '-a':
                show_hidden = True
            elif arg.startswith('-L') and len(arg) > 2:
                try:
                    max_depth = int(arg[2:])
                except:
                    pass
        
        output = [os.path.basename(path) or path]
        
        def build_tree(current_path: str, prefix: str = "", depth: int = 0):
            if max_depth is not None and depth >= max_depth:
                return
            
            try:
                items = sorted(os.listdir(current_path))
                if not show_hidden:
                    items = [item for item in items if not item.startswith('.')]
                
                for i, item in enumerate(items):
                    item_path = os.path.join(current_path, item)
                    is_last = i == len(items) - 1
                    
                    connector = "└── " if is_last else "├── "
                    output.append(f"{prefix}{connector}{item}")
                    
                    if os.path.isdir(item_path):
                        extension = "    " if is_last else "│   "
                        build_tree(item_path, prefix + extension, depth + 1)
                        
            except PermissionError:
                output.append(f"{prefix}[Permission Denied]")
        
        build_tree(path)
        
        return CommandResult(
            success=True,
            output='\n'.join(output),
            exit_code=0,
            command=f"tree {' '.join(args)}"
        )
    
    def du(self, args: List[str]) -> CommandResult:
        """Display disk usage"""
        path = self.terminal.current_directory
        human_readable = '-h' in args
        summarize = '-s' in args
        
        try:
            total_size = 0
            
            if summarize:
                for root, dirs, files in os.walk(path):
                    for file in files:
                        try:
                            total_size += os.path.getsize(os.path.join(root, file))
                        except:
                            pass
                
                size_str = self._human_readable_size(total_size) if human_readable else str(total_size)
                output = f"{size_str}\t{os.path.basename(path) or path}"
            else:
                output = []
                for item in os.listdir(path):
                    item_path = os.path.join(path, item)
                    try:
                        if os.path.isfile(item_path):
                            size = os.path.getsize(item_path)
                            size_str = self._human_readable_size(size) if human_readable else str(size)
                            output.append(f"{size_str}\t{item}")
                        elif os.path.isdir(item_path):
                            dir_size = 0
                            for root, dirs, files in os.walk(item_path):
                                for file in files:
                                    try:
                                        dir_size += os.path.getsize(os.path.join(root, file))
                                    except:
                                        pass
                            size_str = self._human_readable_size(dir_size) if human_readable else str(dir_size)
                            output.append(f"{size_str}\t{item}/")
                    except:
                        output.append(f"?\t{item}")
                output = '\n'.join(output)
            
            return CommandResult(
                success=True,
                output=output,
                exit_code=0,
                command=f"du {' '.join(args)}"
            )
        except Exception as e:
            return CommandResult(
                success=False,
                output="",
                error=str(e),
                exit_code=1,
                command=f"du {' '.join(args)}"
            )
    
    def zip_files(self, args: List[str]) -> CommandResult:
        """Create ZIP archive"""
        if len(args) < 2:
            return CommandResult(
                success=False,
                output="",
                error="Usage: zip <archive_name.zip> <file1> [file2 ...]",
                exit_code=1,
                command="zip"
            )
        
        archive_name = args[0]
        if not archive_name.endswith('.zip'):
            archive_name += '.zip'
        
        archive_path = os.path.join(self.terminal.current_directory, archive_name)
        files = args[1:]
        
        try:
            with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file in files:
                    file_path = os.path.join(self.terminal.current_directory, file)
                    if os.path.exists(file_path):
                        if os.path.isfile(file_path):
                            zipf.write(file_path, file)
                        elif os.path.isdir(file_path):
                            for root, dirs, files_in_dir in os.walk(file_path):
                                for f in files_in_dir:
                                    full_path = os.path.join(root, f)
                                    arcname = os.path.relpath(full_path, self.terminal.current_directory)
                                    zipf.write(full_path, arcname)
            
            return CommandResult(
                success=True,
                output=f"Created archive: {archive_name}",
                exit_code=0,
                command=f"zip {' '.join(args)}"
            )
        except Exception as e:
            return CommandResult(
                success=False,
                output="",
                error=str(e),
                exit_code=1,
                command=f"zip {' '.join(args)}"
            )
    
    def unzip(self, args: List[str]) -> CommandResult:
        """Extract ZIP archive"""
        if not args:
            return CommandResult(
                success=False,
                output="",
                error="Usage: unzip <archive.zip> [destination]",
                exit_code=1,
                command="unzip"
            )
        
        archive_name = args[0]
        archive_path = os.path.join(self.terminal.current_directory, archive_name)
        
        destination = args[1] if len(args) > 1 else os.path.splitext(archive_name)[0]
        dest_path = os.path.join(self.terminal.current_directory, destination)
        
        try:
            with zipfile.ZipFile(archive_path, 'r') as zipf:
                zipf.extractall(dest_path)
            
            return CommandResult(
                success=True,
                output=f"Extracted {archive_name} to {destination}",
                exit_code=0,
                command=f"unzip {' '.join(args)}"
            )
        except Exception as e:
            return CommandResult(
                success=False,
                output="",
                error=str(e),
                exit_code=1,
                command=f"unzip {' '.join(args)}"
            )
    
    def download(self, args: List[str]) -> CommandResult:
        """Download file from URL"""
        if not args:
            return CommandResult(
                success=False,
                output="",
                error="Usage: download <url> [output_filename]",
                exit_code=1,
                command="download"
            )
        
        url = args[0]
        output_filename = args[1] if len(args) > 1 else os.path.basename(url)
        output_path = os.path.join(self.terminal.current_directory, output_filename)
        
        try:
            urllib.request.urlretrieve(url, output_path)
            return CommandResult(
                success=True,
                output=f"Downloaded {url} to {output_filename}",
                exit_code=0,
                command=f"download {' '.join(args)}"
            )
        except Exception as e:
            return CommandResult(
                success=False,
                output="",
                error=str(e),
                exit_code=1,
                command=f"download {' '.join(args)}"
            )


class ProcessManager:
    """Manages system processes"""
    
    def __init__(self, terminal):
        self.terminal = terminal
        self.background_processes: Dict[int, subprocess.Popen] = {}
    
    def ps(self, args: List[str]) -> CommandResult:
        """List running processes"""
        output = []
        
        # Header
        output.append(f"{'PID':<8} {'PPID':<8} {'CPU%':<8} {'MEM%':<8} {'RSS(MB)':<10} {'STATUS':<12} {'NAME':<20}")
        output.append("-" * 80)
        
        for proc in psutil.process_iter(['pid', 'ppid', 'name', 'cpu_percent', 'memory_percent', 'memory_info', 'status']):
            try:
                info = proc.info
                mem_mb = info['memory_info'].rss / 1024 / 1024 if info['memory_info'] else 0
                output.append(
                    f"{info['pid']:<8} "
                    f"{info['ppid']:<8} "
                    f"{info['cpu_percent']:<8.1f} "
                    f"{info['memory_percent']:<8.1f} "
                    f"{mem_mb:<10.1f} "
                    f"{info['status']:<12} "
                    f"{info['name'][:20]:<20}"
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        return CommandResult(
            success=True,
            output='\n'.join(output),
            exit_code=0,
            command="ps"
        )
    
    def kill(self, args: List[str]) -> CommandResult:
        """Terminate processes"""
        if not args:
            return CommandResult(
                success=False,
                output="",
                error="Usage: kill [-9] <pid>",
                exit_code=1,
                command="kill"
            )
        
        force = '-9' in args
        args = [arg for arg in args if arg != '-9']
        
        output = []
        errors = []
        
        for pid_str in args:
            try:
                pid = int(pid_str)
                if force:
                    proc = psutil.Process(pid)
                    proc.kill()
                else:
                    proc = psutil.Process(pid)
                    proc.terminate()
                output.append(f"Terminated process {pid}")
            except ValueError:
                errors.append(f"Invalid PID: {pid_str}")
            except psutil.NoSuchProcess:
                errors.append(f"Process {pid_str} not found")
            except Exception as e:
                errors.append(f"Failed to kill {pid_str}: {str(e)}")
        
        return CommandResult(
            success=len(errors) == 0,
            output='\n'.join(output),
            error='\n'.join(errors) if errors else "",
            exit_code=0 if not errors else 1,
            command=f"kill {' '.join(args)}"
        )
    
    def killall(self, args: List[str]) -> CommandResult:
        """Kill processes by name"""
        if not args:
            return CommandResult(
                success=False,
                output="",
                error="Usage: killall <process_name>",
                exit_code=1,
                command="killall"
            )
        
        process_name = args[0]
        killed = []
        
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if proc.info['name'] and process_name.lower() in proc.info['name'].lower():
                    proc.terminate()
                    killed.append(str(proc.info['pid']))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        if killed:
            return CommandResult(
                success=True,
                output=f"Killed {len(killed)} processes matching '{process_name}'\nPIDs: {', '.join(killed)}",
                exit_code=0,
                command=f"killall {' '.join(args)}"
            )
        else:
            return CommandResult(
                success=False,
                output="",
                error=f"No processes found matching '{process_name}'",
                exit_code=1,
                command=f"killall {' '.join(args)}"
            )
    
    def top(self, args: List[str]) -> CommandResult:
        """Display top processes"""
        processes = []
        
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            try:
                info = proc.info
                processes.append({
                    'pid': info['pid'],
                    'name': info['name'][:30],
                    'cpu': info['cpu_percent'],
                    'mem': info['memory_percent']
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        processes.sort(key=lambda x: x['cpu'], reverse=True)
        processes = processes[:20]
        
        output = [f"{'PID':<8} {'CPU%':<8} {'MEM%':<8} {'NAME':<30}"]
        output.append("-" * 55)
        
        for proc in processes:
            output.append(f"{proc['pid']:<8} {proc['cpu']:<8.1f} {proc['mem']:<8.1f} {proc['name']:<30}")
        
        # System info
        cpu_percent = psutil.cpu_percent(interval=0.5)
        memory = psutil.virtual_memory()
        output.append("")
        output.append(f"CPU Usage: {cpu_percent}%")
        output.append(f"Memory Usage: {memory.percent}% (Used: {memory.used // (1024**3)}GB / Total: {memory.total // (1024**3)}GB)")
        
        return CommandResult(
            success=True,
            output='\n'.join(output),
            exit_code=0,
            command="top"
        )


class NetworkManager:
    """Manages network operations"""
    
    def __init__(self, terminal):
        self.terminal = terminal
    
    def ping(self, args: List[str]) -> CommandResult:
        """Ping a host"""
        if not args:
            return CommandResult(
                success=False,
                output="",
                error="Usage: ping <host> [count]",
                exit_code=1,
                command="ping"
            )
        
        host = args[0]
        count = int(args[1]) if len(args) > 1 else 4
        
        param = '-n' if IS_WINDOWS else '-c'
        
        try:
            result = subprocess.run(
                ['ping', param, str(count), host],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            return CommandResult(
                success=result.returncode == 0,
                output=result.stdout,
                error=result.stderr if result.returncode != 0 else "",
                exit_code=result.returncode,
                command=f"ping {' '.join(args)}"
            )
        except subprocess.TimeoutExpired:
            return CommandResult(
                success=False,
                output="",
                error="Ping timed out",
                exit_code=1,
                command=f"ping {' '.join(args)}"
            )
        except Exception as e:
            return CommandResult(
                success=False,
                output="",
                error=str(e),
                exit_code=1,
                command=f"ping {' '.join(args)}"
            )
    
    def netstat(self, args: List[str]) -> CommandResult:
        """Display network connections"""
        output = []
        
        for conn in psutil.net_connections(kind='inet'):
            try:
                laddr = f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else "-"
                raddr = f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else "-"
                status = conn.status
                pid = conn.pid if conn.pid else "-"
                
                output.append(f"{pid:<8} {laddr:<25} {raddr:<25} {status:<15}")
            except:
                continue
        
        if output:
            header = f"{'PID':<8} {'LOCAL ADDRESS':<25} {'REMOTE ADDRESS':<25} {'STATUS':<15}"
            output.insert(0, header)
            output.insert(1, "-" * 75)
        
        return CommandResult(
            success=True,
            output='\n'.join(output) if output else "No network connections found",
            exit_code=0,
            command="netstat"
        )
    
    def ifconfig(self, args: List[str]) -> CommandResult:
        """Display network interfaces"""
        output = []
        
        for interface, addrs in psutil.net_if_addrs().items():
            output.append(f"\n{interface}:")
            for addr in addrs:
                if addr.family == socket.AF_INET:
                    output.append(f"  IPv4: {addr.address}")
                    if addr.broadcast:
                        output.append(f"  Broadcast: {addr.broadcast}")
                elif addr.family == socket.AF_INET6:
                    output.append(f"  IPv6: {addr.address}")
                elif hasattr(socket, 'AF_PACKET') and addr.family == socket.AF_PACKET:
                    output.append(f"  MAC: {addr.address}")
        
        stats = psutil.net_if_stats()
        for interface, stat in stats.items():
            if stat.isup:
                output.append(f"  Status: UP (Speed: {stat.speed} Mbps)")
            else:
                output.append(f"  Status: DOWN")
        
        return CommandResult(
            success=True,
            output='\n'.join(output),
            exit_code=0,
            command="ifconfig"
        )
    
    def wget(self, args: List[str]) -> CommandResult:
        """Download file from URL (alias for download)"""
        return self.terminal.fs_manager.download(args)
    
    def curl(self, args: List[str]) -> CommandResult:
        """Fetch URL content"""
        if not args:
            return CommandResult(
                success=False,
                output="",
                error="Usage: curl <url>",
                exit_code=1,
                command="curl"
            )
        
        url = args[0]
        
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                content = response.read().decode('utf-8', errors='ignore')
                return CommandResult(
                    success=True,
                    output=content[:10000] + ('...' if len(content) > 10000 else ''),
                    exit_code=0,
                    command=f"curl {' '.join(args)}"
                )
        except Exception as e:
            return CommandResult(
                success=False,
                output="",
                error=str(e),
                exit_code=1,
                command=f"curl {' '.join(args)}"
            )


class PythonManager:
    """Manages Python-related operations"""
    
    def __init__(self, terminal):
        self.terminal = terminal
    
    def run_python(self, args: List[str]) -> CommandResult:
        """Run Python code or script"""
        if not args:
            # Start Python REPL
            return self._start_python_repl()
        
        script = args[0]
        
        try:
            if os.path.exists(os.path.join(self.terminal.current_directory, script)):
                # Run script file
                python_cmd = self.terminal.venv_manager.venv_python_path if self.terminal.venv_manager.current_venv else sys.executable
                result = subprocess.run(
                    [python_cmd, script] + args[1:],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    cwd=self.terminal.current_directory
                )
                
                return CommandResult(
                    success=result.returncode == 0,
                    output=result.stdout,
                    error=result.stderr if result.returncode != 0 else "",
                    exit_code=result.returncode,
                    command=f"python {' '.join(args)}"
                )
            else:
                # Run code string
                python_cmd = self.terminal.venv_manager.venv_python_path if self.terminal.venv_manager.current_venv else sys.executable
                result = subprocess.run(
                    [python_cmd, '-c', script],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                return CommandResult(
                    success=result.returncode == 0,
                    output=result.stdout,
                    error=result.stderr if result.returncode != 0 else "",
                    exit_code=result.returncode,
                    command=f"python {' '.join(args)}"
                )
        except subprocess.TimeoutExpired:
            return CommandResult(
                success=False,
                output="",
                error="Execution timed out",
                exit_code=1,
                command=f"python {' '.join(args)}"
            )
        except Exception as e:
            return CommandResult(
                success=False,
                output="",
                error=str(e),
                exit_code=1,
                command=f"python {' '.join(args)}"
            )
    
    def _start_python_repl(self) -> CommandResult:
        """Start Python interactive REPL"""
        try:
            python_cmd = self.terminal.venv_manager.venv_python_path if self.terminal.venv_manager.current_venv else sys.executable
            subprocess.run([python_cmd], cwd=self.terminal.current_directory)
            return CommandResult(
                success=True,
                output="Python REPL exited",
                exit_code=0,
                command="python"
            )
        except Exception as e:
            return CommandResult(
                success=False,
                output="",
                error=str(e),
                exit_code=1,
                command="python"
            )
    
    def pip(self, args: List[str]) -> CommandResult:
        """Run pip command"""
        if not args:
            return CommandResult(
                success=False,
                output="",
                error="Usage: pip <command> [options]",
                exit_code=1,
                command="pip"
            )
        
        if self.terminal.venv_manager.current_venv:
            pip_cmd = self.terminal.venv_manager.venv_pip_path
        else:
            pip_cmd = shutil.which('pip') or shutil.which('pip3')
        
        if not pip_cmd:
            return CommandResult(
                success=False,
                output="",
                error="pip not found. Please install pip or activate a virtual environment.",
                exit_code=1,
                command="pip"
            )
        
        try:
            result = subprocess.run(
                [pip_cmd] + args,
                capture_output=True,
                text=True,
                timeout=300,
                cwd=self.terminal.current_directory
            )
            
            return CommandResult(
                success=result.returncode == 0,
                output=result.stdout,
                error=result.stderr if result.returncode != 0 else "",
                exit_code=result.returncode,
                command=f"pip {' '.join(args)}"
            )
        except subprocess.TimeoutExpired:
            return CommandResult(
                success=False,
                output="",
                error="Command timed out",
                exit_code=1,
                command=f"pip {' '.join(args)}"
            )
        except Exception as e:
            return CommandResult(
                success=False,
                output="",
                error=str(e),
                exit_code=1,
                command=f"pip {' '.join(args)}"
            )


class SystemManager:
    """Manages system operations"""
    
    def __init__(self, terminal):
        self.terminal = terminal
    
    def whoami(self, args: List[str]) -> CommandResult:
        """Display current user"""
        return CommandResult(
            success=True,
            output=os.getlogin(),
            exit_code=0,
            command="whoami"
        )
    
    def hostname(self, args: List[str]) -> CommandResult:
        """Display hostname"""
        return CommandResult(
            success=True,
            output=platform.node(),
            exit_code=0,
            command="hostname"
        )
    
    def uname(self, args: List[str]) -> CommandResult:
        """Display system information"""
        output = []
        
        if '-a' in args or len(args) == 0:
            output.append(f"System: {platform.system()}")
            output.append(f"Node: {platform.node()}")
            output.append(f"Release: {platform.release()}")
            output.append(f"Version: {platform.version()}")
            output.append(f"Machine: {platform.machine()}")
            output.append(f"Processor: {platform.processor()}")
        else:
            if '-s' in args:
                output.append(platform.system())
            if '-n' in args:
                output.append(platform.node())
            if '-r' in args:
                output.append(platform.release())
            if '-v' in args:
                output.append(platform.version())
            if '-m' in args:
                output.append(platform.machine())
        
        return CommandResult(
            success=True,
            output='\n'.join(output),
            exit_code=0,
            command=f"uname {' '.join(args)}"
        )
    
    def env(self, args: List[str]) -> CommandResult:
        """Display environment variables"""
        env_vars = self.terminal.env_manager.get_all()
        output = '\n'.join([f"{k}={v}" for k, v in sorted(env_vars.items())])
        
        return CommandResult(
            success=True,
            output=output,
            exit_code=0,
            command="env"
        )
    
    def set_env(self, args: List[str]) -> CommandResult:
        """Set environment variable"""
        if not args:
            return CommandResult(
                success=False,
                output="",
                error="Usage: export VAR=value",
                exit_code=1,
                command="export"
            )
        
        output = []
        errors = []
        
        for arg in args:
            if '=' in arg:
                key, value = arg.split('=', 1)
                self.terminal.env_manager.set(key, value, permanent=True)
                output.append(f"Set {key}={value}")
            else:
                errors.append(f"Ignoring invalid format: {arg}")
        
        return CommandResult(
            success=len(errors) == 0,
            output='\n'.join(output),
            error='\n'.join(errors) if errors else "",
            exit_code=0 if not errors else 1,
            command=f"export {' '.join(args)}"
        )
    
    def unset_env(self, args: List[str]) -> CommandResult:
        """Unset environment variable"""
        if not args:
            return CommandResult(
                success=False,
                output="",
                error="Usage: unset VAR",
                exit_code=1,
                command="unset"
            )
        
        output = []
        for var in args:
            self.terminal.env_manager.unset(var)
            output.append(f"Unset {var}")
        
        return CommandResult(
            success=True,
            output='\n'.join(output),
            exit_code=0,
            command=f"unset {' '.join(args)}"
        )
    
    def echo(self, args: List[str]) -> CommandResult:
        """Echo arguments"""
        output = ' '.join(args)
        output = self.terminal.env_manager.expand(output)
        
        return CommandResult(
            success=True,
            output=output,
            exit_code=0,
            command=f"echo {' '.join(args)}"
        )
    
    def clear(self, args: List[str]) -> CommandResult:
        """Clear screen"""
        os.system('cls' if IS_WINDOWS else 'clear')
        return CommandResult(
            success=True,
            output="",
            exit_code=0,
            command="clear"
        )
    
    def exit(self, args: List[str]) -> CommandResult:
        """Exit terminal"""
        self.terminal.running = False
        return CommandResult(
            success=True,
            output="Goodbye!",
            exit_code=0,
            command="exit"
        )
    
    def help(self, args: List[str]) -> CommandResult:
        """Display help"""
        help_text = self.terminal.get_help_text()
        return CommandResult(
            success=True,
            output=help_text,
            exit_code=0,
            command="help"
        )
    
    def history(self, args: List[str]) -> CommandResult:
        """Display command history"""
        history = self.terminal.history_manager.history[-50:] if args else self.terminal.history_manager.history
        
        output = []
        for i, cmd in enumerate(history, 1):
            output.append(f"{i:4}  {cmd}")
        
        if not output:
            output = ["No command history"]
        
        return CommandResult(
            success=True,
            output='\n'.join(output),
            exit_code=0,
            command="history"
        )
    
    def date(self, args: List[str]) -> CommandResult:
        """Display current date and time"""
        now = datetime.now()
        return CommandResult(
            success=True,
            output=now.strftime("%a %b %d %H:%M:%S %Z %Y"),
            exit_code=0,
            command="date"
        )
    
    def cal(self, args: List[str]) -> CommandResult:
        """Display calendar"""
        now = datetime.now()
        import calendar
        
        year = int(args[0]) if args else now.year
        month = int(args[1]) if len(args) > 1 else now.month
        
        cal = calendar.month(year, month)
        
        return CommandResult(
            success=True,
            output=cal,
            exit_code=0,
            command=f"cal {' '.join(args)}"
        )
    
    def sleep(self, args: List[str]) -> CommandResult:
        """Sleep for specified seconds"""
        if not args:
            return CommandResult(
                success=False,
                output="",
                error="Usage: sleep <seconds>",
                exit_code=1,
                command="sleep"
            )
        
        try:
            seconds = float(args[0])
            time.sleep(seconds)
            return CommandResult(
                success=True,
                output=f"Slept for {seconds} seconds",
                exit_code=0,
                command=f"sleep {' '.join(args)}"
            )
        except ValueError:
            return CommandResult(
                success=False,
                output="",
                error="Invalid number",
                exit_code=1,
                command=f"sleep {' '.join(args)}"
            )
    
    def which(self, args: List[str]) -> CommandResult:
        """Locate a command"""
        if not args:
            return CommandResult(
                success=False,
                output="",
                error="Usage: which <command>",
                exit_code=1,
                command="which"
            )
        
        command = args[0]
        path = shutil.which(command)
        
        if path:
            return CommandResult(
                success=True,
                output=path,
                exit_code=0,
                command=f"which {' '.join(args)}"
            )
        else:
            return CommandResult(
                success=False,
                output="",
                error=f"{command} not found",
                exit_code=1,
                command=f"which {' '.join(args)}"
            )
    
    def alias(self, args: List[str]) -> CommandResult:
        """Manage aliases"""
        if not args:
            # List all aliases
            aliases = self.terminal.alias_manager.list_aliases()
            if aliases:
                output = "Aliases:\n" + '\n'.join([f"  alias {k}='{v}'" for k, v in aliases.items()])
            else:
                output = "No aliases defined"
            return CommandResult(
                success=True,
                output=output,
                exit_code=0,
                command="alias"
            )
        
        # Parse alias name='command'
        full_command = ' '.join(args)
        if '=' not in full_command:
            return CommandResult(
                success=False,
                output="",
                error="Usage: alias name='command'",
                exit_code=1,
                command="alias"
            )
        
        name, command = full_command.split('=', 1)
        name = name.strip()
        command = command.strip("'\"")
        
        if self.terminal.alias_manager.add_alias(name, command):
            return CommandResult(
                success=True,
                output=f"Alias created: {name} -> {command}",
                exit_code=0,
                command=f"alias {name}='{command}'"
            )
        else:
            return CommandResult(
                success=False,
                output="",
                error="Invalid alias name",
                exit_code=1,
                command="alias"
            )
    
    def unalias(self, args: List[str]) -> CommandResult:
        """Remove an alias"""
        if not args:
            return CommandResult(
                success=False,
                output="",
                error="Usage: unalias <name>",
                exit_code=1,
                command="unalias"
            )
        
        name = args[0]
        if self.terminal.alias_manager.remove_alias(name):
            return CommandResult(
                success=True,
                output=f"Alias removed: {name}",
                exit_code=0,
                command=f"unalias {name}"
            )
        else:
            return CommandResult(
                success=False,
                output="",
                error=f"Alias '{name}' not found",
                exit_code=1,
                command=f"unalias {name}"
            )


class TerminalEmulator:
    """Full-featured Terminal Emulator"""
    
    def __init__(self, output_callback: Callable = None, input_callback: Callable = None):
        """
        Initialize terminal emulator
        
        Args:
            output_callback: Function to call for output (for web integration)
            input_callback: Function to call for input (for web integration)
        """
        # Set workspace as root - this is the ONLY directory the terminal can see
        # Get the actual workspace.json directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        workspace_root = script_dir
        
        # If there's a workspace.json in parent, use that directory
        if os.path.exists(os.path.join(script_dir, 'workspace.json')):
            workspace_root = script_dir
        elif os.path.exists(os.path.join(script_dir, '..', 'workspace.json')):
            workspace_root = os.path.dirname(script_dir)
        
        self.workspace_root = workspace_root
        self.current_directory = workspace_root
        os.chdir(workspace_root)
        self.running = True
        self.output_callback = output_callback
        self.input_callback = input_callback
        
        # Initialize managers
        self.env_manager = EnvironmentManager()
        self.history_manager = HistoryManager()
        self.alias_manager = AliasManager()
        self.venv_manager = VirtualEnvironmentManager(self)
        self.fs_manager = FileSystemManager(self)
        self.process_manager = ProcessManager(self)
        self.network_manager = NetworkManager(self)
        self.python_manager = PythonManager(self)
        self.system_manager = SystemManager(self)
        
        # Command handlers mapping
        self.command_handlers: Dict[str, Callable] = {
            # Navigation
            'cd': self.fs_manager.cd,
            'pwd': self.fs_manager.pwd,
            'ls': self.fs_manager.ls,
            'dir': self.fs_manager.ls,
            'tree': self.fs_manager.tree,
            
            # File operations
            'mkdir': self.fs_manager.mkdir,
            'rmdir': self.fs_manager.rmdir,
            'rm': self.fs_manager.rm,
            'cp': self.fs_manager.cp,
            'copy': self.fs_manager.cp,
            'mv': self.fs_manager.mv,
            'move': self.fs_manager.mv,
            'touch': self.fs_manager.touch,
            'cat': self.fs_manager.cat,
            'type': self.fs_manager.cat,
            'head': self.fs_manager.head,
            'tail': self.fs_manager.tail,
            'find': self.fs_manager.find,
            'grep': self.fs_manager.grep,
            'du': self.fs_manager.du,
            
            # Archive operations
            'zip': self.fs_manager.zip_files,
            'unzip': self.fs_manager.unzip,
            
            # Download operations
            'download': self.fs_manager.download,
            'wget': self.network_manager.wget,
            'curl': self.network_manager.curl,
            
            # Process management
            'ps': self.process_manager.ps,
            'kill': self.process_manager.kill,
            'killall': self.process_manager.killall,
            'top': self.process_manager.top,
            
            # Network
            'ping': self.network_manager.ping,
            'netstat': self.network_manager.netstat,
            'ifconfig': self.network_manager.ifconfig,
            'ipconfig': self.network_manager.ifconfig,
            
            # Python
            'python': self.python_manager.run_python,
            'python3': self.python_manager.run_python,
            'pip': self.python_manager.pip,
            'pip3': self.python_manager.pip,
            
            # Virtual Environment
            'venv': self.venv_command,
            'deactivate': lambda args: self.venv_manager.deactivate_venv(),
            
            # System
            'whoami': self.system_manager.whoami,
            'hostname': self.system_manager.hostname,
            'uname': self.system_manager.uname,
            'env': self.system_manager.env,
            'export': self.system_manager.set_env,
            'set': self.system_manager.set_env,
            'unset': self.system_manager.unset_env,
            'echo': self.system_manager.echo,
            'clear': self.system_manager.clear,
            'cls': self.system_manager.clear,
            'exit': self.system_manager.exit,
            'quit': self.system_manager.exit,
            'help': self.system_manager.help,
            'history': self.system_manager.history,
            'date': self.system_manager.date,
            'cal': self.system_manager.cal,
            'sleep': self.system_manager.sleep,
            'which': self.system_manager.which,
            'alias': self.system_manager.alias,
            'unalias': self.system_manager.unalias,
        }
    
    def venv_command(self, args: List[str]) -> CommandResult:
        """Virtual environment management command"""
        if not args:
            output = "Virtual Environment Commands:\n"
            output += "  venv create <name>           - Create new virtual environment\n"
            output += "  venv create <name> -p <path> - Create venv at specific path\n"
            output += "  venv activate <name>         - Activate virtual environment\n"
            output += "  venv deactivate              - Deactivate current venv\n"
            output += "  venv list                    - List all venvs in current directory\n"
            output += "  venv install <package>       - Install package in active venv\n"
            output += "  venv uninstall <package>     - Uninstall package from active venv\n"
            output += "  venv list-packages           - List installed packages\n"
            output += "  venv freeze [file]           - Generate requirements.txt\n"
            output += "  venv install-reqs [file]     - Install from requirements.txt\n"
            output += "  venv info                    - Show active venv information"
            return CommandResult(
                success=True,
                output=output,
                exit_code=0,
                command="venv"
            )
        
        subcommand = args[0]
        
        if subcommand == "create":
            if len(args) < 2:
                return CommandResult(
                    success=False,
                    output="",
                    error="Usage: venv create <name> [-p <path>]",
                    exit_code=1,
                    command="venv create"
                )
            name = args[1]
            path = None
            if '-p' in args:
                p_idx = args.index('-p')
                if p_idx + 1 < len(args):
                    path = args[p_idx + 1]
            return self.venv_manager.create_venv(name, path)
        
        elif subcommand == "activate":
            if len(args) < 2:
                return CommandResult(
                    success=False,
                    output="",
                    error="Usage: venv activate <name>",
                    exit_code=1,
                    command="venv activate"
                )
            return self.venv_manager.activate_venv(args[1])
        
        elif subcommand == "deactivate":
            return self.venv_manager.deactivate_venv()
        
        elif subcommand == "list":
            return self.venv_manager.list_venvs()
        
        elif subcommand == "install":
            if len(args) < 2:
                return CommandResult(
                    success=False,
                    output="",
                    error="Usage: venv install <package> [version]",
                    exit_code=1,
                    command="venv install"
                )
            package = args[1]
            version = args[2] if len(args) > 2 else None
            return self.venv_manager.install_package(package, version)
        
        elif subcommand == "uninstall":
            if len(args) < 2:
                return CommandResult(
                    success=False,
                    output="",
                    error="Usage: venv uninstall <package>",
                    exit_code=1,
                    command="venv uninstall"
                )
            return self.venv_manager.uninstall_package(args[1])
        
        elif subcommand == "list-packages":
            return self.venv_manager.list_packages()
        
        elif subcommand == "freeze":
            filename = args[1] if len(args) > 1 else "requirements.txt"
            return self.venv_manager.freeze_requirements(filename)
        
        elif subcommand == "install-reqs":
            filename = args[1] if len(args) > 1 else "requirements.txt"
            return self.venv_manager.install_requirements(filename)
        
        elif subcommand == "info":
            info = self.venv_manager.get_venv_info()
            if info["active"]:
                output = f"Active Virtual Environment:\n"
                output += f"  Name: {info['name']}\n"
                output += f"  Path: {info['path']}\n"
                output += f"  Python: {info['python']}\n"
                output += f"  Pip: {info['pip']}"
            else:
                output = "No virtual environment is currently active"
            return CommandResult(
                success=True,
                output=output,
                exit_code=0,
                command="venv info"
            )
        
        else:
            return CommandResult(
                success=False,
                output="",
                error=f"Unknown venv subcommand: {subcommand}",
                exit_code=1,
                command=f"venv {subcommand}"
            )
    
    def get_prompt(self) -> str:
        """Get the terminal prompt string - PowerShell style with friendly path"""
        venv_indicator = ""
        if self.venv_manager.current_venv:
            venv_indicator = f"({self.venv_manager.current_venv}) "
        
        # Get friendly path using the fs_manager's method
        friendly_path = self.fs_manager._get_friendly_path(self.current_directory)
        
        # PowerShell style prompt: PS HenAi:\Workspace\subfolder>
        return f"{Colors.GREEN}{venv_indicator}PS{Colors.RESET} {Colors.CYAN}{friendly_path}{Colors.RESET}> "
    
    def get_plain_prompt(self) -> str:
        """Get plain text prompt (for web integration)"""
        venv_indicator = ""
        if self.venv_manager.current_venv:
            venv_indicator = f"({self.venv_manager.current_venv}) "
        
        friendly_path = self.fs_manager._get_friendly_path(self.current_directory)
        return f"{venv_indicator}PS {friendly_path}> "
    
    def execute_command(self, command_line: str) -> CommandResult:
        """
        Execute a command and return the result
        
        Args:
            command_line: The command line to execute
            
        Returns:
            CommandResult object with output and status
        """
        if not command_line or not command_line.strip():
            return CommandResult(success=True, output="", exit_code=0, command="")
        
        start_time = time.time()
        
        # Add to history
        self.history_manager.add_command(command_line)
        
        # Expand aliases
        command_line = self.alias_manager.expand(command_line)
        
        # Parse command
        parts = self._parse_command_line(command_line)
        if not parts:
            return CommandResult(success=True, output="", exit_code=0, command=command_line)
        
        command = parts[0].lower()
        args = parts[1:]
        
        # Handle pipes
        if '|' in command_line:
            return self._handle_pipes(command_line)
        
        # Handle output redirection
        if '>' in command_line:
            return self._handle_redirection(command_line, '>')
        if '>>' in command_line:
            return self._handle_redirection(command_line, '>>')
        
        # Handle background execution
        background = False
        if args and args[-1] == '&':
            background = True
            args = args[:-1]
        
        # Execute built-in command
        if command in self.command_handlers:
            handler = self.command_handlers[command]
            result = handler(args)
            
            # If this was a cd command, update the current directory in the result
            if command == 'cd' and result.success and result.output:
                # The output contains the new friendly path
                pass
        else:
            # Execute as system command
            result = self._execute_system_command(command_line)
        
        result.execution_time = time.time() - start_time
        result.command = command_line
        
        # Handle background execution
        if background and result.success:
            result.output = f"[Background] {result.output}"
        
        return result
    
    def _parse_command_line(self, command_line: str) -> List[str]:
        """Parse command line respecting quotes"""
        import shlex
        try:
            return shlex.split(command_line)
        except ValueError:
            # Fallback to simple split
            return command_line.split()
    
    def _execute_system_command(self, command: str) -> CommandResult:
        """Execute a system command using subprocess"""
        try:
            shell = IS_WINDOWS
            
            process = subprocess.Popen(
                command,
                shell=shell,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=self.current_directory,
                env=self.env_manager.get_all()
            )
            
            stdout, stderr = process.communicate(timeout=300)
            
            return CommandResult(
                success=process.returncode == 0,
                output=stdout,
                error=stderr if process.returncode != 0 else "",
                exit_code=process.returncode,
                command=command
            )
            
        except subprocess.TimeoutExpired:
            process.kill()
            return CommandResult(
                success=False,
                output="",
                error="Command timed out after 300 seconds",
                exit_code=124,
                command=command
            )
        except FileNotFoundError:
            return CommandResult(
                success=False,
                output="",
                error=f"Command not found: {command.split()[0] if command else command}",
                exit_code=127,
                command=command
            )
        except Exception as e:
            return CommandResult(
                success=False,
                output="",
                error=str(e),
                exit_code=1,
                command=command
            )
    
    def _handle_pipes(self, command_line: str) -> CommandResult:
        """Handle pipe operations between commands"""
        commands = [cmd.strip() for cmd in command_line.split('|')]
        
        processes = []
        prev_output = None
        
        for i, cmd in enumerate(commands):
            parts = self._parse_command_line(cmd)
            if not parts:
                continue
            
            if parts[0] in self.command_handlers:
                # Built-in command - can't pipe easily, execute directly
                handler = self.command_handlers[parts[0]]
                result = handler(parts[1:])
                if prev_output:
                    result.output = prev_output + result.output
                prev_output = result.output
            else:
                # External command
                try:
                    if prev_output:
                        # Pass previous output as input
                        process = subprocess.Popen(
                            cmd,
                            shell=IS_WINDOWS,
                            stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            cwd=self.current_directory
                        )
                        stdout, stderr = process.communicate(input=prev_output, timeout=60)
                    else:
                        process = subprocess.Popen(
                            cmd,
                            shell=IS_WINDOWS,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            cwd=self.current_directory
                        )
                        stdout, stderr = process.communicate(timeout=60)
                    
                    prev_output = stdout
                    if stderr:
                        prev_output += stderr
                        
                except Exception as e:
                    return CommandResult(
                        success=False,
                        output="",
                        error=f"Pipe error: {str(e)}",
                        exit_code=1,
                        command=command_line
                    )
        
        return CommandResult(
            success=True,
            output=prev_output or "",
            exit_code=0,
            command=command_line
        )
    
    def _handle_redirection(self, command_line: str, redir_op: str) -> CommandResult:
        """Handle output redirection to files"""
        parts = command_line.split(redir_op, 1)
        if len(parts) != 2:
            return self._execute_system_command(command_line)
        
        command = parts[0].strip()
        filename = parts[1].strip()
        
        result = self.execute_command(command)
        
        if result.success or result.output:
            mode = 'a' if redir_op == '>>' else 'w'
            try:
                filepath = os.path.join(self.current_directory, filename)
                with open(filepath, mode, encoding='utf-8') as f:
                    f.write(result.output)
                result.output = f"Output written to {filename}"
            except Exception as e:
                result.error = f"Failed to write to {filename}: {str(e)}"
                result.success = False
        
        return result
    
    def get_help_text(self) -> str:
        """Get help text for all commands"""
        return f"""
{Colors.BOLD}{Colors.CYAN}═══════════════════════════════════════════════════════════════════════════════{Colors.RESET}
{Colors.BOLD}HenAi Terminal Emulator v2.0 - Complete Command Reference{Colors.RESET}
{Colors.BOLD}{Colors.CYAN}═══════════════════════════════════════════════════════════════════════════════{Colors.RESET}

{Colors.BOLD}{Colors.GREEN}📁 NAVIGATION & FILE OPERATIONS{Colors.RESET}
  {Colors.YELLOW}cd [dir]{Colors.RESET}        - Change directory
  {Colors.YELLOW}pwd{Colors.RESET}             - Print working directory
  {Colors.YELLOW}ls [-a] [-l] [-h] [-R]{Colors.RESET} - List directory contents
  {Colors.YELLOW}tree [-a] [-L N]{Colors.RESET} - Display directory tree
  {Colors.YELLOW}mkdir [-p] <dir>{Colors.RESET} - Create directory
  {Colors.YELLOW}rmdir <dir>{Colors.RESET}      - Remove empty directory
  {Colors.YELLOW}rm [-r] [-f] <file>{Colors.RESET} - Remove files/directories
  {Colors.YELLOW}cp [-r] <src> <dst>{Colors.RESET} - Copy files/directories
  {Colors.YELLOW}mv <src> <dst>{Colors.RESET}    - Move/rename files
  {Colors.YELLOW}touch <file>{Colors.RESET}     - Create file or update timestamp
  {Colors.YELLOW}cat <file>{Colors.RESET}       - Display file contents
  {Colors.YELLOW}head [-n N] <file>{Colors.RESET} - Display first N lines
  {Colors.YELLOW}tail [-n N] <file>{Colors.RESET} - Display last N lines
  {Colors.YELLOW}find -name <pattern>{Colors.RESET} - Search for files
  {Colors.YELLOW}grep [-i] <pattern> <file>{Colors.RESET} - Search in files
  {Colors.YELLOW}du [-h] [-s]{Colors.RESET}     - Disk usage

{Colors.BOLD}{Colors.GREEN}🐍 PYTHON & VIRTUAL ENVIRONMENT{Colors.RESET}
  {Colors.YELLOW}python [script]{Colors.RESET}  - Run Python code/REPL
  {Colors.YELLOW}pip <command>{Colors.RESET}     - Python package manager
  {Colors.YELLOW}venv create <name>{Colors.RESET} - Create virtual environment
  {Colors.YELLOW}venv activate <name>{Colors.RESET} - Activate venv
  {Colors.YELLOW}venv deactivate{Colors.RESET}   - Deactivate venv
  {Colors.YELLOW}venv list{Colors.RESET}        - List virtual environments
  {Colors.YELLOW}venv install <package>{Colors.RESET} - Install package in venv
  {Colors.YELLOW}venv freeze [file]{Colors.RESET} - Generate requirements.txt

{Colors.BOLD}{Colors.GREEN}📦 ARCHIVE & DOWNLOAD{Colors.RESET}
  {Colors.YELLOW}zip <archive.zip> <files...>{Colors.RESET} - Create ZIP archive
  {Colors.YELLOW}unzip <archive.zip> [dest]{Colors.RESET} - Extract ZIP
  {Colors.YELLOW}download <url> [filename]{Colors.RESET} - Download file
  {Colors.YELLOW}wget <url>{Colors.RESET}        - Download file (alias)
  {Colors.YELLOW}curl <url>{Colors.RESET}        - Fetch URL content

{Colors.BOLD}{Colors.GREEN}🔧 PROCESS MANAGEMENT{Colors.RESET}
  {Colors.YELLOW}ps{Colors.RESET}               - List processes
  {Colors.YELLOW}top{Colors.RESET}              - Display top processes
  {Colors.YELLOW}kill [-9] <pid>{Colors.RESET}  - Terminate process
  {Colors.YELLOW}killall <name>{Colors.RESET}   - Kill processes by name

{Colors.BOLD}{Colors.GREEN}🌐 NETWORK{Colors.RESET}
  {Colors.YELLOW}ping <host> [count]{Colors.RESET} - Ping a host
  {Colors.YELLOW}netstat{Colors.RESET}          - Network connections
  {Colors.YELLOW}ifconfig{Colors.RESET}         - Network interfaces

{Colors.BOLD}{Colors.GREEN}⚙️ SYSTEM{Colors.RESET}
  {Colors.YELLOW}whoami{Colors.RESET}           - Current user
  {Colors.YELLOW}hostname{Colors.RESET}         - System hostname
  {Colors.YELLOW}uname [-a]{Colors.RESET}       - System information
  {Colors.YELLOW}env{Colors.RESET}              - Environment variables
  {Colors.YELLOW}export VAR=value{Colors.RESET} - Set environment variable
  {Colors.YELLOW}echo <text>{Colors.RESET}      - Display text
  {Colors.YELLOW}clear{Colors.RESET}            - Clear screen
  {Colors.YELLOW}date{Colors.RESET}             - Current date/time
  {Colors.YELLOW}cal [month] [year]{Colors.RESET} - Calendar
  {Colors.YELLOW}sleep <seconds>{Colors.RESET}  - Delay execution
  {Colors.YELLOW}which <command>{Colors.RESET}  - Locate command
  {Colors.YELLOW}alias name='command'{Colors.RESET} - Create alias
  {Colors.YELLOW}unalias <name>{Colors.RESET}   - Remove alias
  {Colors.YELLOW}history{Colors.RESET}          - Command history
  {Colors.YELLOW}help{Colors.RESET}             - This help
  {Colors.YELLOW}exit{Colors.RESET}             - Exit terminal

{Colors.BOLD}{Colors.CYAN}═══════════════════════════════════════════════════════════════════════════════{Colors.RESET}

{Colors.DIM}Tips:
  • Use ↑/↓ to navigate command history
  • Use Tab for command completion
  • Use | to pipe commands (e.g., ls | grep py)
  • Use > to redirect output to file (e.g., ls > files.txt)
  • Use & to run command in background
  • Type 'venv' for virtual environment help{Colors.RESET}
"""
    
    def run_interactive(self):
        """Run terminal in interactive mode (for console)"""
        print(self.get_help_text())
        
        while self.running:
            try:
                command = input(self.get_prompt())
                result = self.execute_command(command)
                
                if result.output:
                    print(result.output)
                if result.error:
                    print(f"{Colors.RED}{result.error}{Colors.RESET}")
                    
            except KeyboardInterrupt:
                print("^C")
                continue
            except EOFError:
                print()
                break
            except Exception as e:
                print(f"{Colors.RED}Error: {str(e)}{Colors.RESET}")
        
        print(f"\n{Colors.GREEN}Goodbye!{Colors.RESET}")
    
    def execute_and_get_output(self, command: str) -> Dict[str, Any]:
        """
        Execute command and return output as dict (for web integration)
        
        Returns:
            Dict with keys: success, output, error, exit_code, execution_time
        """
        result = self.execute_command(command)
        return {
            "success": result.success,
            "output": result.output,
            "error": result.error,
            "exit_code": result.exit_code,
            "execution_time": result.execution_time,
            "command": result.command
        }


def create_terminal_blueprint(app):
    """Create Flask blueprint for terminal endpoints"""
    from flask import Blueprint, request, jsonify, session
    
    terminal_bp = Blueprint('terminal', __name__, url_prefix='/api/terminal')
    
    # Store terminal instances per session
    terminals = {}
    
    @terminal_bp.route('/execute', methods=['POST'])
    def execute():
        """Execute a command in the terminal"""
        data = request.json
        command = data.get('command', '')
        session_id = data.get('session_id', 'default')
        
        if session_id not in terminals:
            terminals[session_id] = TerminalEmulator()
        
        terminal = terminals[session_id]
        result = terminal.execute_and_get_output(command)
        
        return jsonify(result)
    
    @terminal_bp.route('/cwd', methods=['GET'])
    def get_cwd():
        """Get current working directory"""
        session_id = request.args.get('session_id', 'default')
        
        if session_id not in terminals:
            terminals[session_id] = TerminalEmulator()
        
        terminal = terminals[session_id]
        return jsonify({"cwd": terminal.current_directory})
    
    @terminal_bp.route('/cwd', methods=['POST'])
    def set_cwd():
        """Set current working directory"""
        data = request.json
        path = data.get('path', '')
        session_id = data.get('session_id', 'default')
        
        if session_id not in terminals:
            terminals[session_id] = TerminalEmulator()
        
        terminal = terminals[session_id]
        
        if os.path.exists(path) and os.path.isdir(path):
            terminal.current_directory = path
            os.chdir(path)
            return jsonify({"success": True, "cwd": path})
        else:
            return jsonify({"success": False, "error": "Directory not found"}), 404
    
    @terminal_bp.route('/info', methods=['GET'])
    def get_info():
        """Get terminal information"""
        session_id = request.args.get('session_id', 'default')
        
        if session_id not in terminals:
            terminals[session_id] = TerminalEmulator()
        
        terminal = terminals[session_id]
        
        return jsonify({
            "cwd": terminal.current_directory,
            "platform": platform.system(),
            "python_version": sys.version,
            "venv_active": terminal.venv_manager.current_venv is not None,
            "venv_name": terminal.venv_manager.current_venv
        })
    
    @terminal_bp.route('/reset', methods=['POST'])
    def reset_terminal():
        """Reset terminal session"""
        data = request.json
        session_id = data.get('session_id', 'default')
        
        terminals[session_id] = TerminalEmulator()
        
        return jsonify({"success": True})
    
    @terminal_bp.route('/venv/activate', methods=['POST'])
    def activate_venv():
        """Activate a virtual environment"""
        data = request.json
        name = data.get('name', '')
        path = data.get('path', None)
        session_id = data.get('session_id', 'default')
        
        if session_id not in terminals:
            terminals[session_id] = TerminalEmulator()
        
        terminal = terminals[session_id]
        result = terminal.venv_manager.activate_venv(name, path)
        
        return jsonify({
            "success": result.success,
            "output": result.output,
            "error": result.error
        })
    
    @terminal_bp.route('/venv/deactivate', methods=['POST'])
    def deactivate_venv():
        """Deactivate current virtual environment"""
        data = request.json
        session_id = data.get('session_id', 'default')
        
        if session_id not in terminals:
            terminals[session_id] = TerminalEmulator()
        
        terminal = terminals[session_id]
        result = terminal.venv_manager.deactivate_venv()
        
        return jsonify({
            "success": result.success,
            "output": result.output,
            "error": result.error
        })
    
    @terminal_bp.route('/venv/list', methods=['GET'])
    def list_venvs():
        """List virtual environments"""
        session_id = request.args.get('session_id', 'default')
        path = request.args.get('path', None)
        
        if session_id not in terminals:
            terminals[session_id] = TerminalEmulator()
        
        terminal = terminals[session_id]
        result = terminal.venv_manager.list_venvs(path)
        
        return jsonify({
            "success": result.success,
            "output": result.output,
            "error": result.error
        })
    
    @terminal_bp.route('/files', methods=['GET'])
    def list_files():
        """List files in current directory"""
        session_id = request.args.get('session_id', 'default')
        path = request.args.get('path', None)
        
        if session_id not in terminals:
            terminals[session_id] = TerminalEmulator()
        
        terminal = terminals[session_id]
        
        target_path = path if path else terminal.current_directory
        
        try:
            items = []
            for item in os.listdir(target_path):
                item_path = os.path.join(target_path, item)
                items.append({
                    "name": item,
                    "path": item_path,
                    "is_dir": os.path.isdir(item_path),
                    "size": os.path.getsize(item_path) if os.path.isfile(item_path) else 0,
                    "modified": datetime.fromtimestamp(os.path.getmtime(item_path)).isoformat()
                })
            
            items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
            
            return jsonify({
                "success": True,
                "cwd": target_path,
                "files": items
            })
        except Exception as e:
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500
    
    return terminal_bp


def main():
    """Main entry point for standalone terminal"""
    terminal = TerminalEmulator()
    terminal.run_interactive()


if __name__ == "__main__":
    main()
from __future__ import print_function, annotations
import socket
import os
import stat
import typing as t
from pathlib import Path

def showlanip() -> socket._RetAddress:
    s = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    s.connect(("8.8.8.8",80))
    ip = s.getsockname()[0]
    s.close()
    return ip

def clearscreen() -> None:
    if os.name == "nt":
        os.system("cls")
    else:
        os.system("clear")

def fixreadonly(func: t.Any,path: Path | str) -> None:
    try:
        if isinstance(path, Path):
            path.chmod(path.stat().st_mode | stat.S_IWRITE)
        else:
            os.chmod(path,stat.S_IWRITE)
        func(path)
    except Exception:
        pass

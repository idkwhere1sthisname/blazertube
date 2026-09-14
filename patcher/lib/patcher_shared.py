from __future__ import print_function
import socket
import os
import stat

def showlanip():
    s = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    s.connect(("8.8.8.8",80))
    ip = s.getsockname()[0]
    s.close()
    return ip

def clearscreen():
    if os.name == "nt":
        os.system("cls")
    else:
        os.system("clear")

def fixreadonly(func,path):
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass
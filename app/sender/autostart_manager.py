import os
import sys
import winreg


REGISTRY_RUN_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
REGISTRY_VALUE_NAME = "SenderApp"


def get_autostart_command() -> str:
    """Return command stored in Windows Run registry entry."""
    if getattr(sys, "frozen", False):
        return sys.executable

    script_path = os.path.abspath(sys.argv[0])
    python_path = sys.executable
    return f'"{python_path}" "{script_path}"'


def register_autostart() -> bool:
    """Register sender in current user Windows autostart."""
    try:
        command = get_autostart_command()
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            REGISTRY_RUN_KEY,
            0,
            winreg.KEY_SET_VALUE,
        )
        winreg.SetValueEx(key, REGISTRY_VALUE_NAME, 0, winreg.REG_SZ, command)
        winreg.CloseKey(key)
        print(f"[INFO] Aplikacja zarejestrowana w autostarcie: {command}")
        return True
    except Exception as exc:
        print(f"[ERROR] Nie udalo sie zarejestrowac autostartu: {exc}")
        return False


def unregister_autostart() -> bool:
    """Remove sender from current user Windows autostart."""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            REGISTRY_RUN_KEY,
            0,
            winreg.KEY_SET_VALUE,
        )
        winreg.DeleteValue(key, REGISTRY_VALUE_NAME)
        winreg.CloseKey(key)
        print("[INFO] Aplikacja usunieta z autostartu")
        return True
    except FileNotFoundError:
        print("[INFO] Aplikacja nie byla w autostarcie")
        return True
    except Exception as exc:
        print(f"[ERROR] Nie udalo sie usunac z autostartu: {exc}")
        return False


def is_registered() -> bool:
    """Check whether sender is already registered in current user autostart."""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            REGISTRY_RUN_KEY,
            0,
            winreg.KEY_READ,
        )
        winreg.QueryValueEx(key, REGISTRY_VALUE_NAME)
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return False
    except Exception:
        return False


def setup_autostart() -> None:
    """Ensure sender autostart entry exists."""
    if not is_registered():
        print("[INFO] Konfigurowanie autostartu...")
        if register_autostart():
            print("[SUCCESS] Autostart skonfigurowany pomyslnie!")
        else:
            print("[ERROR] Nie udalo sie skonfigurowac autostartu")
    else:
        print("[INFO] Autostart jest juz skonfigurowany")

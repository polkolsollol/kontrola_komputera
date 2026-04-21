import winreg
import sys
import os

def register_autostart():
    """Rejestruje aplikację w autostarcie Windows."""
    try:
        # Pobierz ścieżkę do aktualnego exe
        if getattr(sys, 'frozen', False):
            # Jeśli to exe (PyInstaller/cx_Freeze)
            exe_path = sys.executable
        else:
            # Jeśli to skrypt Python
            exe_path = os.path.abspath(sys.argv[0])
        
        # Otwórz klucz rejestru autostartu
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE
        )
        
        # Dodaj wpis
        winreg.SetValueEx(key, "SenderApp", 0, winreg.REG_SZ, exe_path)
        winreg.CloseKey(key)
        
        print(f"[INFO] Aplikacja zarejestrowana w autostarcie: {exe_path}")
        return True
        
    except Exception as e:
        print(f"[ERROR] Nie udało się zarejestrować autostartu: {e}")
        return False

def unregister_autostart():
    """Usuwa aplikację z autostartu."""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE
        )
        
        winreg.DeleteValue(key, "SenderApp")
        winreg.CloseKey(key)
        
        print("[INFO] Aplikacja usunięta z autostartu")
        return True
        
    except FileNotFoundError:
        print("[INFO] Aplikacja nie była w autostarcie")
        return True
    except Exception as e:
        print(f"[ERROR] Nie udało się usunąć z autostartu: {e}")
        return False

def is_registered():
    """Sprawdza czy aplikacja jest już w autostarcie."""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_READ
        )
        
        value, _ = winreg.QueryValueEx(key, "SenderApp")
        winreg.CloseKey(key)
        return True
        
    except FileNotFoundError:
        return False
    except Exception:
        return False

def setup_autostart():
    """Główna funkcja do konfiguracji autostartu."""
    if not is_registered():
        print("[INFO] Konfigurowanie autostartu...")
        if register_autostart():
            print("[SUCCESS] Autostart skonfigurowany pomyślnie!")
        else:
            print("[ERROR] Nie udało się skonfigurować autostartu")
    else:
        print("[INFO] Autostart już skonfigurowany")
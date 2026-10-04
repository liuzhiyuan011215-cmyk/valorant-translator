import os
import sys
import subprocess

def create_shortcuts():
    desktop = os.path.join(os.path.expanduser('~'), 'Desktop')
    target_dir = os.path.dirname(os.path.abspath(__file__))
    # Launch with pythonw so no console window pops up (output goes to logs\translator.log)
    pythonw = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')

    # Desktop .lnk shortcut via PowerShell
    lnk_path = os.path.join(desktop, '瓦语通 - AI 实时同传.lnk')
    ps_cmd = (
        f"$WshShell = New-Object -comObject WScript.Shell; "
        f"$Shortcut = $WshShell.CreateShortcut('{lnk_path}'); "
        f"$Shortcut.TargetPath = '{pythonw}'; "
        f"$Shortcut.Arguments = 'main.py'; "
        f"$Shortcut.WorkingDirectory = '{target_dir}'; "
        f"$Shortcut.Description = '瓦罗兰特 AI 实时同传双语字幕系统'; "
        f"$Shortcut.Save()"
    )
    subprocess.run(['powershell', '-Command', ps_cmd], check=True)
    print(f"Created Desktop LNK: {lnk_path}")

if __name__ == '__main__':
    create_shortcuts()

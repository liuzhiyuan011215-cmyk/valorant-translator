import sys
import os

# Ensure project directory is in python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 用 pythonw 启动（不弹黑色命令行窗口）时 print 和报错无处可去：写进 logs/translator.log，出问题时可以查
if sys.stdout is None or sys.stderr is None:
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "translator.log")
    mode = "w" if os.path.exists(log_path) and os.path.getsize(log_path) > 1_000_000 else "a"
    sys.stdout = sys.stderr = open(log_path, mode, encoding="utf-8", buffering=1)

from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow

def main():
    # Enable High DPI scaling for crisp rendering on high resolution displays
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
    
    app = QApplication(sys.argv)
    app.setApplicationName("ValoVoice Translator")
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()

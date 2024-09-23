#script to launch refrig application
import sys
from refrig_gui_main import refrigMainWindow

from PySide6.QtWidgets import (QApplication, QMainWindow)

app = QApplication(sys.argv)
mw = QMainWindow()
window = refrigMainWindow(mw)
mw.showMaximized()

app.exec()

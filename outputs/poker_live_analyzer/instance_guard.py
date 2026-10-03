"""同一份個人資料只允許一個主程式，第二次開啟時喚回視窗。"""
import hashlib
from PySide6.QtCore import QLockFile
from PySide6.QtNetwork import QLocalServer, QLocalSocket

class InstanceGuard:
    def __init__(self, directory):
        self.lock = QLockFile(str(directory / 'application.lock'))
        self.lock.setStaleLockTime(0)
        self.name = 'PokerLens-' + hashlib.sha256(str(directory).encode()).hexdigest()[:20]
        self.server = None

    def acquire(self):
        if not self.lock.tryLock(0):
            socket = QLocalSocket()
            socket.connectToServer(self.name)
            if socket.waitForConnected(500):
                socket.write(b'show')
                socket.waitForBytesWritten(500)
                socket.disconnectFromServer()
            return False
        QLocalServer.removeServer(self.name)
        self.server = QLocalServer()
        if not self.server.listen(self.name):
            self.lock.unlock()
            raise RuntimeError('無法建立程式視窗連線')
        return True

    def bind(self, window):
        def activate():
            socket = self.server.nextPendingConnection()
            if socket:
                socket.close()
                socket.deleteLater()
            window.showNormal()
            window.raise_()
            window.activateWindow()
        self.server.newConnection.connect(activate)

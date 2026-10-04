"""Real socket protocol peer used by runtime tests, independent of CLI code."""
import json
import socket

class Peer:
    def __init__(self, path, role='cli'):
        self.socket = socket.socket(socket.AF_UNIX)
        self.socket.settimeout(3)
        self.socket.connect(str(path))
        self.reader = self.socket.makefile('rb')
        self.seq = 0
        self.send({'type':'hello', 'role':role})
        self.greeting = self.read()

    def send(self, frame):
        self.socket.sendall((json.dumps({'protocolVersion':2, **frame})+'\n').encode())

    def read(self):
        line = self.reader.readline()
        if not line:
            raise EOFError('peer closed')
        return json.loads(line)

    def call(self, method, **args):
        self.seq += 1
        self.send({'type':'command', 'seq':self.seq, 'method':method, 'args':args})
        while True:
            frame = self.read()
            if frame['type'] == 'reply' and frame['seq'] == self.seq:
                return frame

    def close(self):
        self.reader.close()
        self.socket.close()

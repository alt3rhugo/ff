"""Windows stub for the Unix-only `termios` module.

google-colab-cli imports `termios` at load time (for its interactive console /
repl). On native Windows Python that module does not exist, so every command —
including the non-interactive ones we use (new/upload/exec/download/stop) —
crashes on import. orchestrate.py puts this directory on PYTHONPATH when it
shells out to `colab` on Windows so the import succeeds. The interactive
console/repl are not used by the orchestrator.
"""

TCSADRAIN = 1
TCSANOW = 0
TCSAFLUSH = 2
ECHO = 8
ICANON = 2


class error(Exception):
	pass


def tcgetattr(fd):
	return [0, 0, 0, 0, 0, 0, []]


def tcsetattr(fd, when, attrs):
	return None


def tcflush(fd, queue):
	return None

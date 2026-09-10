"""Offline model transport. Images implement one JSON request/response on stdin/stdout."""
import json
import os
import re
import selectors
import subprocess
import time
import uuid

MAX_RESPONSE = 1024 * 1024


class IsolatedModel:
    def __init__(self, image, timeout=120):
        # Require an immutable local image ID: no implicit pulls or tag drift.
        if not re.fullmatch(r'sha256:[a-f0-9]{64}', image):
            raise ValueError('Use a local immutable Docker image ID (sha256:...)')
        self.image, self.timeout = image, timeout

    def __call__(self, messages, turn):
        from run import TOOLS
        name = 'ehr-model-'+uuid.uuid4().hex
        command = ['docker', 'run', '--rm', '-i', '--name', name, '--pull=never',
                   '--network=none', '--no-healthcheck', '--ipc=none', '--read-only', '--user=65532:65532',
                   '--cap-drop=ALL', '--security-opt=no-new-privileges:true',
                   '--pids-limit=128', '--memory=8g', '--memory-swap=8g', '--cpus=4',
                   '--ulimit=nofile=256:256', '--ulimit=core=0:0', '--log-driver=none',
                   '--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=256m', self.image]
        # Reject image-declared mounts and injected environment; model weights and
        # executable must be baked into a separately built, answer-free image.
        info = json.loads(subprocess.check_output(['docker','image','inspect',self.image], timeout=15))[0]
        if info['Config'].get('Volumes'):
            raise ValueError('Model image must not declare volumes')
        request = json.dumps({'messages': messages, 'tools': TOOLS}).encode()+b'\n'
        if len(request) > 4 * MAX_RESPONSE:
            raise ValueError('Model context budget exceeded')
        # A file as stdin avoids deadlock if an adversarial model never reads input.
        import tempfile
        with tempfile.TemporaryFile() as source:
            source.write(request); source.seek(0)
            proc = subprocess.Popen(command, stdin=source, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            selector = selectors.DefaultSelector()
            selector.register(proc.stdout, selectors.EVENT_READ)
            raw = bytearray()
            deadline = time.monotonic()+self.timeout
            try:
                while True:
                    if time.monotonic() >= deadline:
                        raise TimeoutError('Model execution timed out')
                    if not selector.select(min(0.2, max(0, deadline-time.monotonic()))):
                        continue
                    chunk = os.read(proc.stdout.fileno(), 65536)
                    if not chunk:
                        break
                    raw.extend(chunk)
                    if len(raw) > MAX_RESPONSE:
                        raise ValueError('Model response budget exceeded')
                if proc.wait(timeout=max(0.01, deadline-time.monotonic())):
                    raise RuntimeError('Model container failed')
                data = json.loads(raw)
                message = data['message']
                if not isinstance(message, dict) or message.get('role') != 'assistant':
                    raise ValueError('Expected assistant message')
                # Provider-specific extra fields must never enter the next prompt.
                return {k:v for k,v in message.items() if k in {'role','content','tool_calls'}}, {}
            finally:
                selector.close()
                proc.stdout.close()
                if proc.poll() is None:
                    proc.kill()
                proc.wait()
                subprocess.run(['docker','rm','-f',name], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=15, check=False)

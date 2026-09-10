"""Adversarial runtime fixture: no benchmark inputs or answers in this image."""
import json
import os
from pathlib import Path
import socket
import sys

request = json.load(sys.stdin)
assert set(request) == {'messages', 'tools'}
assert os.getuid() == 65532
# Some kernels expose inactive tunnel devices even with network=none.
assert not Path('/proc/net/route').read_text().splitlines()[1:]
import fcntl, struct
with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as control:
    for _, name in socket.if_nameindex():
        flags = struct.unpack_from('H', fcntl.ioctl(control, 0x8913, struct.pack('256s', name.encode())), 16)[0]
        assert name == 'lo' or not flags & 1, 'Active interface: '+name
for path in ['/evaluation-private', '/data', '/benchmark-tasks', '/var/run/docker.sock',
             '/Users/enryu/EHR-Benchmark-Sandbox']:
    assert not Path(path).exists(), path
try:
    Path('/probe-write').write_text('escape')
except OSError:
    pass
else:
    raise AssertionError('Writable root')
for host, port in [('1.1.1.1',443), ('8.8.8.8',53), ('169.254.169.254',80), ('127.0.0.1',8090)]:
    try:
        s = socket.create_connection((host,port),timeout=1)
    except OSError:
        pass
    else:
        s.close()
        raise AssertionError('Network escape')
if not any(m['role'] == 'tool' for m in request['messages']):
    pid = request['messages'][-1]['content'].split()[-1]
    message = {'role':'assistant','content':None,'tool_calls':[{'id':'probe', 'type':'function',
               'function':{'name':'read_task','arguments':json.dumps({'patient_id':pid})}}]}
else:
    message = {'role':'assistant','content':'{"choice":"A","choice_set":"standalone"}'}
print(json.dumps({'message':message}))

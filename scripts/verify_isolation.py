"""Fail-closed verification of the actual running EHR container."""
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ['docker','compose','-f','docker-compose.yml','-f','benchmark-ehr/compose.yml']

def output(command):
    return subprocess.check_output(command, cwd=ROOT, text=True)

cid = output(COMPOSE+['ps','-q','ehr-viewer']).strip()
if not cid or '\n' in cid:
    raise SystemExit('FAIL: exactly one running EHR viewer is required')
info = json.loads(output(['docker','inspect',cid]))[0]
host = info['HostConfig']
assert info['State']['Running'], 'Viewer is not running'
assert host['ReadonlyRootfs'] and 'ALL' in host['CapDrop'], 'Missing filesystem/capability isolation'
assert 'no-new-privileges:true' in host['SecurityOpt'], 'Missing privilege restriction'
assert info['Config']['User'] == '65532:65532', 'Viewer must be non-root'
assert not host['Privileged'], 'Privileged container'
assert len(info['Mounts']) == 1, 'Unexpected mounts'
mount = info['Mounts'][0]
assert mount['Destination'] == '/data' and not mount['RW'], 'Data must be read-only'
assert Path(mount['Source']).resolve() == ROOT/'benchmark-ehr/generated', 'Unexpected data source'
for network in info['NetworkSettings']['Networks']:
    config = json.loads(output(['docker','network','inspect',network]))[0]
    assert config['Internal'], 'External network attached'
assert not host.get('PortBindings'), 'Strict Docker viewer must not publish ports'
for bindings in info['NetworkSettings']['Ports'].values():
    for binding in bindings or []:
        assert binding['HostIp'] == '127.0.0.1', 'Non-loopback port exposed'
probe = '''
import json, socket, urllib.request
with urllib.request.urlopen('http://127.0.0.1:8090/api/patients', timeout=5) as r:
    assert len(json.load(r)) == 500
blocked = []
for host, port in [('1.1.1.1',443),('8.8.8.8',53),('169.254.169.254',80)]:
    try:
        sock = socket.create_connection((host,port),timeout=2)
    except OSError:
        blocked.append(host)
    else:
        sock.close()
        raise RuntimeError('Unexpected egress to '+host)
print(json.dumps({'healthy':True,'blocked':blocked}))
'''
result = json.loads(output(['docker','exec',cid,'python','-c',probe]))
assert result == {'healthy':True,'blocked':['1.1.1.1','8.8.8.8','169.254.169.254']}
print('PASS: running EHR snapshot, mounts, privilege controls, network topology and egress probes')

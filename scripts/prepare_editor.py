import hashlib
import json
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1]
LOCK = json.loads((ROOT / 'editor/lock.json').read_text())


def derive_editor(source):
    if len(source) != LOCK['sourceBytes'] or hashlib.sha256(source).hexdigest() != LOCK['sourceSha256']:
        raise RuntimeError('Native editor source checksum mismatch; the unchanged pinned client.swf is required.')
    for edit in LOCK['edits']:
        offset, before = edit['offset'], bytes.fromhex(edit['before'])
        if source[offset:offset + len(before)] != before:
            raise RuntimeError(f"Native editor entry target mismatch: {edit['reason']} at {offset}")
    result = source
    for edit in reversed(LOCK['edits']):
        offset, before, after = edit['offset'], bytes.fromhex(edit['before']), bytes.fromhex(edit['after'])
        result = result[:offset] + after + result[offset + len(before):]
    if len(result) != LOCK['outputBytes'] or hashlib.sha256(result).hexdigest() != LOCK['outputSha256']:
        raise RuntimeError('Native editor derived checksum mismatch; inspect the entry transform and source lock.')
    return result


def prepare_editor():
    result = derive_editor((ROOT / LOCK['source']).read_bytes())
    target = ROOT / LOCK['artifact']
    if target.exists():
        if target.read_bytes() != result:
            raise RuntimeError(f'Native editor artifact checksum mismatch: {target}; preserve and inspect the corrupt artifact.')
    else:
        with tempfile.NamedTemporaryFile(dir=ROOT, prefix='.editor-stage-', delete=False) as staged:
            staged.write(result)
            temporary = Path(staged.name)
        temporary.replace(target)
    print(f"Prepared reconstructed native editor: {LOCK['outputSha256']}", flush=True)


if __name__ == '__main__':
    prepare_editor()

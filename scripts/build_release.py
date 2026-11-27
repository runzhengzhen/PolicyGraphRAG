"""Build a source ZIP using only the reviewed public file set."""
import hashlib
import json
import zipfile
from pathlib import Path
from check_release import ROOT, inspect_artifact, source_files


def main():
    files, problems = source_files()
    if problems:
        raise RuntimeError(json.dumps(problems, ensure_ascii=False))
    version = '0.2.0'
    prefix = 'policy-graphrag-workbench-' + version
    manifest = {'version': version, 'license': 'MIT', 'files': [
        {'path': p.relative_to(ROOT).as_posix(), 'bytes': p.stat().st_size,
         'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(files)]}
    output = ROOT / 'dist' / (prefix + '-source.zip')
    output.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(str(output), 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for entry in manifest['files']:
            archive.write(str(ROOT / entry['path']), prefix + '/' + entry['path'])
        archive.writestr(prefix + '/release-manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
    with zipfile.ZipFile(str(output)) as archive:
        for entry in manifest['files']:
            assert hashlib.sha256(archive.read(prefix + '/' + entry['path'])).hexdigest() == entry['sha256']
    audit = inspect_artifact(output)
    if audit['problems']:
        raise RuntimeError(json.dumps(audit['problems'], ensure_ascii=False))
    receipt = {'artifact': output.name, 'bytes': output.stat().st_size,
               'sha256': hashlib.sha256(output.read_bytes()).hexdigest(), 'files': len(files) + 1,
               'per_file_hashes': 'passed', 'public_scope_and_content_scan': 'passed'}
    output.with_suffix('.receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

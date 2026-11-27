"""Audit public source/artifact files without opening excluded private folders."""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
TOP_FILES = {'LICENSE', 'THIRD_PARTY_NOTICES.md', 'README.md', 'CONTRIBUTING.md', 'SECURITY.md',
             'CHANGELOG.md', 'CITATION.cff', 'pyproject.toml', 'MANIFEST.in', 'run_demo.sh', '.env.example', '.gitignore'}
DIRECTORIES = {'policygraph', 'tests', 'scripts', 'docs', 'examples', 'config', 'skills', '.github'}
SKIP_DIRS = {'.git', '.venv', '__pycache__', 'outputs', 'data', 'private', 'dist', 'build'}
PATTERNS = {
    'home_directory': re.compile(r'/' + r'(?:Users|home)/[A-Za-z0-9_.-]+/|[A-Z]:\\Users\\[^\\]+\\'),
    'api_token': re.compile(r'\bsk-[A-Za-z0-9_-]{16,}|\bAIza[A-Za-z0-9_-]{25,}'),
    'private_key': re.compile(r'BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY'),
}
TEXT_EXTENSIONS = {'.py', '.md', '.json', '.jsonl', '.csv', '.tsv', '.toml', '.yml', '.yaml', '.sh', '.cff', '.in', '.txt', '.svg'}


def is_public_name(name):
    path = PurePosixPath(name)
    return (not path.is_absolute() and '..' not in path.parts
            and (name in TOP_FILES or (len(path.parts) > 1 and path.parts[0] in DIRECTORIES))
            and not any(part in SKIP_DIRS or part.endswith('.egg-info') for part in path.parts)
            and (path.name != '.env' and not (path.name.startswith('.env.') and path.name != '.env.example'))
            and path.suffix.lower() not in {'.pyc', '.db', '.sqlite3', '.pdf', '.docx', '.ipynb', '.zip', '.mp3', '.wav', '.bin', '.safetensors'})


def inspect_content(name, data):
    problems = []
    try:
        text = data.decode('utf-8')
    except UnicodeError:
        return [{'file': name, 'reason': 'unexpected_binary'}]
    for reason, pattern in PATTERNS.items():
        for match in pattern.finditer(text):
            problems.append({'file': name, 'reason': reason, 'line': text.count('\n', 0, match.start()) + 1})
    return problems


def source_files(root=ROOT):
    files, problems = [], []
    for base, dirs, names in os.walk(str(root)):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.endswith('.egg-info')]
        for name in sorted(names):
            path = Path(base, name)
            relative = path.relative_to(root).as_posix()
            if relative in {'release-manifest.json', 'PKG-INFO', 'setup.cfg'}:
                problems.extend(inspect_content(relative, path.read_bytes()))
                continue
            if path.is_symlink() or not is_public_name(relative):
                problems.append({'file': relative, 'reason': 'outside_public_scope'})
            else:
                files.append(path)
                problems.extend(inspect_content(relative, path.read_bytes()))
    git = subprocess.run(['git', 'ls-files', '-z'], cwd=str(root), capture_output=True, text=True) if shutil.which('git') else None
    if git is not None and git.returncode == 0:
        for name in filter(None, git.stdout.split('\0')):
            if not is_public_name(name):
                problems.append({'file': name, 'reason': 'tracked_nonpublic_file'})
    return files, problems


def inspect_artifact(path):
    path = Path(path)
    members, problems = [], []
    if path.suffix in {'.zip', '.whl'}:
        with zipfile.ZipFile(str(path)) as archive:
            for info in archive.infolist():
                if not info.is_dir():
                    members.append((info.filename, archive.read(info)))
    elif path.name.endswith('.tar.gz'):
        with tarfile.open(str(path), 'r:gz') as archive:
            for member in archive.getmembers():
                if member.issym() or member.islnk():
                    problems.append({'file': member.name, 'reason': 'unexpected_link'})
                elif member.isfile():
                    members.append((member.name, archive.extractfile(member).read()))
    else:
        raise ValueError('Supported artifacts: ZIP, wheel, tar.gz')
    paths = []
    for name, data in members:
        p = PurePosixPath(name)
        if path.suffix == '.whl':
            valid = (len(p.parts) > 1 and (p.parts[0] == 'policygraph' or p.parts[0].endswith('.dist-info')))
        else:
            relative = PurePosixPath(*p.parts[1:]).as_posix()
            valid = is_public_name(relative) or relative in {'release-manifest.json', 'PKG-INFO', 'setup.cfg'} or '.egg-info/' in relative
        if p.is_absolute() or '..' in p.parts or not valid:
            problems.append({'file': name, 'reason': 'outside_public_scope'})
        problems.extend(inspect_content(name, data))
        paths.append(name)
    if len(paths) != len(set(paths)):
        problems.append({'reason': 'duplicate_archive_paths'})
    return {'files': len(members), 'problems': problems}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--artifact', type=Path)
    args = parser.parse_args()
    if args.artifact:
        result = inspect_artifact(args.artifact)
    else:
        files, problems = source_files()
        result = {'files': len(files), 'problems': problems}
    result['status'] = 'passed' if not result['problems'] else 'failed'
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result['problems']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()

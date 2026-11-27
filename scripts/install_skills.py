"""Install portable skills without replacing user-modified skills."""
import argparse
import shutil
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--destination', type=Path, default=Path.home() / '.codex/skills')
    args = parser.parse_args()
    sources = sorted((Path(__file__).resolve().parents[1] / 'skills').glob('*/SKILL.md'))
    for source in sources:
        target = args.destination / source.parent.name / 'SKILL.md'
        if target.exists() and target.read_bytes() != source.read_bytes():
            raise FileExistsError('Existing skill differs; refusing overwrite: ' + target.parent.name)
    for source in sources:
        target = args.destination / source.parent.name / 'SKILL.md'
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(source), str(target))
        print(source.parent.name)


if __name__ == '__main__':
    main()

#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
from pathlib import Path

# Automatically inject local .venv packages if not in an activated virtual environment
BASE_DIR = Path(__file__).resolve().parent
venv_path = BASE_DIR / '.venv'
if venv_path.exists() and not os.environ.get('VIRTUAL_ENV'):
    if os.name == 'nt':
        site_packages = venv_path / 'Lib' / 'site-packages'
        venv_bin = venv_path / 'Scripts'
    else:
        site_packages = next(venv_path.glob('lib/python*/site-packages'), None)
        venv_bin = venv_path / 'bin'

    if site_packages and site_packages.exists():
        sys.path.insert(0, str(site_packages))
        os.environ['PATH'] = str(venv_bin) + os.pathsep + os.environ.get('PATH', '')
        os.environ['VIRTUAL_ENV'] = str(venv_path)



def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'carbonbridge.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()

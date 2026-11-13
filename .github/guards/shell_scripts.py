#!/usr/bin/env python3
import subprocess
import sys


def tracked():
    found = subprocess.run(["git", "ls-files", "-z", "*.sh"],
                           capture_output=True, text=True, check=False)
    # @req> GUARD-83168738@zhoOQpGgBd9R naop4o
    if found.returncode != 0:
        raise SystemExit(f"cannot list shell scripts: {found.stderr.strip()}")
    return sorted(path for path in found.stdout.split("\0") if path)


# @req> GUARD-79122074@9WbEAGS3ea8D igdxho
def main():
    scripts = tracked()
    return subprocess.run(["shellcheck", *scripts], check=False).returncode if scripts else 0


# @req> GUARD-79122074@9WbEAGS3ea8D njx4m6
if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
import subprocess
import sys


def scripts():
    found = subprocess.run(["git", "ls-files", "-z", "*.sh"],
                           capture_output=True, text=True, check=False)
    # @req> GUARD-83168738@zhoOQpGgBd9R jp34lz
    if found.returncode != 0:
        raise SystemExit(f"cannot list shell scripts: {found.stderr.strip()}")
    return sorted(path for path in found.stdout.split("\0") if path)


# @req+ GUARD-79122074@9WbEAGS3ea8D ottz22
def main():
    held = scripts()
    if not held:
        return 0
    if subprocess.run(["shellcheck", "--", *held], check=False).returncode:
        print("::error::shellcheck reports findings in tracked shell scripts "
              "-- fix each one")
        return 1
    return 0
# @req- ottz22


# @req> GUARD-79122074@9WbEAGS3ea8D mwk6y4
if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
import subprocess
import sys

from references import tracked


# @req> GUARD-79122074@9WbEAGS3ea8D mryak2
def main():
    held = tracked(":(top)*.sh")
    if held and subprocess.run(["shellcheck", "--", *held],
                               check=False).returncode:
        print("::error::shellcheck reports findings in tracked shell scripts "
              "-- fix each one")
        return 1
    return 0


# @req> GUARD-79122074@9WbEAGS3ea8D mwk6y4
if __name__ == "__main__":
    sys.exit(main())

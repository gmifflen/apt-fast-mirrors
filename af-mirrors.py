#!/usr/bin/env python3

from subprocess import run, PIPE, STDOUT, check_output
import os
from shlex import quote
import sys
import re
import fileinput

# ensure script is run with root privilages
if not os.geteuid() == 0:
    sys.exit("\nOnly root can run this script\n")

# ensure the script is executed with Python 3.10 or newer.
if sys.version_info < (3, 10):
    sys.exit("This script requires Python 3.10 or newer.")

# prevents  localized output for commands
os.environ['LC_ALL'] = "C"

def get_lsb_info():
    """gathers distribution information using the lsb_release command.

    Returns:
        dict: contains keys 'Distributor ID' and 'Codename' with their respective values.
    """
    try:
        output = check_output(["lsb_release", "-a"], text=True)
        info = {}
        for line in output.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                info[key.strip()] = value.strip()
        return info
    except Exception as e:
        print(f"Failed to get distribution information: {e}")
        sys.exit(1)

# get distribution info
lsb_info = get_lsb_info()
distribution = lsb_info.get("Distributor ID", "Debian").lower()
repo = lsb_info.get("Codename", "stable") # switched from testing to stable, cause it's solid


print("Searching for fastest mirrors...")

# use netselect-apt to find fastest debian mirrors
process = run(
    [
        "/usr/bin/netselect-apt", repo, "-n", "-s",
        "-o /etc/apt/sources.list.d/sources_stable.list"
    ],
    text=True,
    stdout=PIPE,
    stderr=STDOUT,
    env=os.environ

mirrors = []
state = "fastest"

# parse netselect-apt output for mirrors
for line in p.stdout.readlines():
    if state == "fastest" and "fastest" in line:
        state = "http"
    elif state == "http":
        match = re.match("\s*(http\S+)", line)
        if match:
            mirrors.append(match.group(1))
            print(match.group(1))
        elif "Of the hosts" in line:
            state = "finished"


def judge_mirror(entry):
    """checks if an entry should be replaced with a list of mirrors.
    if the entry is part of the distribution, it's replaced by the fastest mirrors.

    Args:
        entry (str): original mirror entry from the apt-fast configuration

    Returns:
        tuple: tuple containing the modified entry (if applicable) and a boolean indicating if a change was made
    """
    if entry is None:
        return entry, False

    lead = entry.partition(',')[0].partition(' ')[0].rstrip('/')
    if lead.endswith(distribution):
        return (','.join(mirrors), True)
    return (entry, False)


found_mirrors = False
in_mirrors = False
mirror_toks = []
advert = '# Mirrors obtained from apt-fast-mirrors\n'

with fileinput.input("/etc/apt-fast.conf", inplace=True) as f:
    for line in f:
        if not in_mirrors:
            tokens = line.split()
            match tokens:
                case ['MIRRORS', '=', '(']:
                    if found_mirrors:
                        sys.stderr.write("apt-fast.conf has than one MIRRORS.")
                    found_mirrors = True
                    in_mirrors = True
                    print(advert, end='')
                    print('MIRRORS=(', end='')
                case _:
                    print(line, end='')
        else:
            tokens = line.strip().split()
            match tokens:
                case [')']:
                    in_mirrors = False
                    print(' '.join(quote(judge_mirror(mirror)[0]) for mirror in mirror_toks) + ' )')
                    mirror_toks = []
                case _:
                    mirror_toks.extend(tokens)

# if no MIRRORS was found in apt-fast.conf, append one to the end
if not found_mirrors:
    print("couldn't find MIRRORS var, appending one to the end")
    with open("/etc/apt-fast.conf", "a") as myfile:
        myfile.write(f'{advert}MIRRORS=({quote(",".join(mirrors))})')

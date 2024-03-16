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
    ["/usr/bin/netselect-apt", repo, "-n", "-s", "-o", "/etc/apt/sources.list.d/sources_stable.list"],
    text=True,
    stdout=PIPE,
    stderr=STDOUT,
    env=os.environ
)

mirrors = []
state = "fastest"

# parse netselect-apt output for mirrors
for line in process.stdout.splitlines():
    if state == "fastest" and "fastest" in line:
        state = "http"
    elif state == "http":
        match = re.match("\s*(http\S+)", line)
        if match:
            mirrors.append(match.group(1))
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
new_content = []
in_mirrors_section = False
mirrors_updated = False
advert = '# Mirrors obtained from apt-fast-mirrors\n'

# proccess apt-fast.conf
for line in fileinput.input("/etc/apt-fast.conf", inplace=False):
    stripped_line = line.strip()
    if stripped_line.startswith("MIRRORS=(") and not mirrors_updated:
        # found MIRRORS line
        print("Updating MIRRORS in /etc/apt-fast.conf.")

        in_mirrors_section = True
        found_mirrors = True
        new_content.append(advert)
        new_content.append('MIRRORS=(')
        new_content.append(' '.join(quote(mirror) for mirror in mirrors) + ' )')
        mirrors_updated = True
    elif in_mirrors_section and stripped_line.endswith(")"):
        # end of MIRRORS section; skip appending this line to prevent duplicate
        in_mirrors_section = False
        continue
    elif not in_mirrors_section:
        # for lines outside the MIRRORS section, add them to the new content as is
        new_content.append(line.rstrip('\n'))

# check if MIRRORS was found; if not, append it
if not found_mirrors:
    print("MIRRORS not found. Adding it to /etc/apt-fast.conf.")
    new_content.append(advert)
    new_content.append('MIRRORS=(' + ' '.join(quote(mirror) for mirror in mirrors) + ' )')

print("The following mirrors have been added to your MIRRORS:")
for mirror in mirrors:
    print(mirror)

# rewrite the /etc/apt-fast.conf file with the updated content
with open("/etc/apt-fast.conf", "w") as f:
    for line in new_content:
        print(line, file=f)

print("Your /etc/apt-fast.conf has been successfully updated.")

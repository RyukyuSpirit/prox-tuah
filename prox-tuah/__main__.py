import sys
import yaml
import glob
import os
import argparse
from .TUAH import TUAH
from proxmoxer import ProxmoxAPI
from .ProxmoxHandler import ProxmoxHandler
from yamlinclude import YamlIncludeConstructor
from pathlib import Path

def load_context(context_dir):
    """
    loads all contexts in given context_dir
    """
    context = {'context': {}}

    files = glob.glob(os.path.join(context_dir, "*.yaml")) + glob.glob(os.path.join(context_dir, '*.yml'))

    # setup yaml constructor to allow includes
    current_dir = os.path.dirname(os.path.abspath(__file__))
    include_constructor = YamlIncludeConstructor(base_dir=current_dir)
    yaml.SafeLoader.add_constructor('!inc', include_constructor)

    for f in sorted(files):
        with open(f, 'r') as file:
            try:
                c = yaml.safe_load(file)
                if isinstance(c, dict):
                    c_name = os.path.splitext(os.path.basename(f))[0]
                    context['context'].update(c)
                else:
                    print(f"Warning: {f} did not load as a dictionary")
            except yaml.YAMLError as exc:
                print(f"Error parsing YAML file {f}: {exc}")

    return context


if __name__ == "__main__":
    context = load_context(f"{Path(__file__).parent}/context.d")
    command = None
    command_file = None
    script_file = None
    interactive = True

    # config argparser
    parser = argparse.ArgumentParser(description="Proxmox text-based user and administration handler")
    parser.add_argument("-c", metavar="<command>", type=str, help="Run this commeand (in quotes, non-interactive mode)")
    parser.add_argument("-f", metavar="<src_file>", type=str, help="Run commands in specified file (non-interactive mode)")
    parser.add_argument("-i", action="store_true", help="Run in interactive mode (default), or enter interactive mode after running command (-c) or file (-f)")
    parser.add_argument("-n", metavar="<node>", type=str, help="Node IP or hostname")
    parser.add_argument("-p", metavar="<password>", type=str, help="Authentication password (used instead of token, if both present)")
    parser.add_argument("-r", metavar="<realm>", type=str, help="Authentication realm (<pam|pve|ldap_domain>)")
    parser.add_argument("-s", metavar="<dst_file>", type=str, help="Script all commands to specified file")
    parser.add_argument("-t", metavar="<token_name>", type=str, help="Authenticate token name")
    parser.add_argument("-T", metavar="<token_value>", type=str, help="Authenticate token value")
    parser.add_argument("-u", metavar="<user>", type=str, help="Username")


    args = parser.parse_args()

    user = None
    password = None
    token_name = None
    token_value = None
    node = None
    realm = None

    if args.c:
        command = args.c

    if args.f:
        command_file = args.f

    if (command or command_file) and not args.i:
        interactive = False

    if args.n:
        node = args.n

    if args.p:
        password = args.p

    if args.r:
        realm = args.r

    if args.s:
        script_file = args.s

    if args.t:
        token_name = args.t

    if args.T:
        token_value = args.T

    if args.u:
        user = args.u

    try:
        handler = ProxmoxHandler(user=user, realm=realm, password=password, token_name=token_name, token_value=token_value, node=node)
    except ValueError as e:
        print(f"  ERROR: {e}")
        sys.exit()

    tuah = TUAH(handler, context)
    tuah.start(interactive=interactive, command=command, command_file=command_file, script_file=script_file)
import sys
import yaml
import glob
import os
from TUAH import TUAH
from proxmoxer import ProxmoxAPI
from VMContext import VMMainContext
from ProxmoxHandler import ProxmoxHandler
from yamlinclude import YamlIncludeConstructor

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

    for f in files:
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
    handler = ProxmoxHandler()
    context = load_context('context.d') 

    tuah = TUAH(handler, context)
    tuah.start()

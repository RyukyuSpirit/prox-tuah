import sys
import os
from TUAH import TUAH
from pprint import pprint
from pathlib import Path

class APIContext(TUAH):
    """"
    VM Context 
    """
    def __init__(self, pm, context={}):
        super().__init__()
        self.prompt = "VM# "
        self.pm = pm 
        self.context = context
    
    def do_list(self, argline):
        """
        List VMs
        """
        print("\nVMID: VM NAME")
        print("--------------")
        for vmid, vm in self.vms.items():
            print(f"{vmid}: {vm['name']}")
        print("")

    def default(self, line):
        """
        Catch-all for non-defined commands
        """
        first = line.split()[0]

        if first.isdigit():
            if first in self.vms.keys():
                VMContext(self.pm, first).cmdloop()
            else:
                print(f"Error: VMID {first} not found")
        else:
            print("Unrecognized command")

class VMContext(TUAH):
    """"
    VM Context 
    """
    def __init__(self, pm, vmid):
        super().__init__()
        self.pm = pm 
        self.vm = self.pm.get_vm(vmid)
        self.prompt = f"VM {vmid} ({self.vm['name']}) # "

    def do_show(self, argline):
        """
        Show VM details 
        """
        print(f"\n  VM {self.vm['vmid']} ({'name'})")
        print("  --------------")
        for field,value in self.vm.items():
            print(f"  {field}: {value}")

    def do_connect(self, argline):
        """
        Connect to VM
        """
        spice_conf = self.pm.get_spice_config(self.vm['vmid'], self.vm['node'])

        filename = self.pm.config.get('spice_file', 'tmp_spice.vv')

        # write spice_conf to formatted spice file
        try:
            with open(filename, "w") as f:
                f.write("[virt-viewer]\n")
                for k,v in spice_conf.items():
                    f.write(f"{k}={v}\n") 
        except IOError as e:
            print(f"Error creating {filename}: {e}")
        
        # open spice file with spice client
        try:
            spice_client = Path(self.pm.config.get('spice_client_path', 'remote-viewer'))
            subprocess.Popen([str(spice_client), filename], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"\n  Launched spice client\n")
        except Exception as e:
            print("Error occurred launching spice client: {e}")









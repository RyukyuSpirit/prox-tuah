import yaml
import re
import subprocess
from proxmoxer import ProxmoxAPI
from pprint import pprint
from pathlib import Path

class ProxmoxHandler(ProxmoxAPI):
    """
    Interface for interacting with Proxmox API
    """
    def __init__(self, config_path='config.yaml', **kwargs):
        self.config = self.load_config(config_path)

        super().__init__(self.config['server'], user=f'{self.config["user"]}@{self.config["realm"]}', password=self.config['password'], verify_ssl=self.config.get('verify_ssl', False), **kwargs)


    def load_config(self, config_path="config.yaml"):
        """
        Loads config
        """
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            return config
        except FileNotFoundError:
            print(f"Error: Configuration file '{config_path}' not found.")
            return None
        except yaml.YAMLError as e:
            print(f"Error parsing YAML file: {e}")
            return None


    def get_vms(self):
        return [vm for vm in self.cluster.resources.get() if vm.get('type') == 'qemu' and vm.get('template') == 0]

    def get_vms_dict(self):
        vms = {}
        for vm in self.get_vms():
            vms.update({str(vm['vmid']): vm})
        return vms

    def get_vm(self, vmid):
        return self.get_vms_dict().get(vmid)

    def get_vms_name_list(self, *args, **kwargs):
        return [{vm['vmid']: vm['name']} for vm in self.get_vms()]

    def get_vms_brief(self):
        return [{'vmid': vm['vmid'], 'name': vm['name'], 'node': vm['node'], 'status': vm['status']} for vm in self.get_vms()]

    def get_templates_list(self):
        return [vm for vm in self.cluster.resources.get() if vm.get('type') == 'qemu' and vm.get('template') == 1]

    def get_templates_name_list(self):
        return [{vm['vmid']: vm['name']} for vm in self.get_templates_list()]

    def get_spice_config(self, vmid, node):
        spice_conf = self.nodes(node).qemu(vmid).spiceproxy.create()

        custom_hosts = self.config.get('custom_hosts')
        if custom_hosts:
            url = spice_conf['proxy']
            host = url.split("//")[1].split(':')[0]
            if host in custom_hosts.keys():
              old_host = host
              url = f"http://{custom_hosts[host]}:3128"
              spice_conf["proxy"] = url
        return spice_conf

    def rawdog_dotted(self, call):
        """
        Accepts function call in dotted notation and attempts to run it on self
        """
        try:
            results = eval(f"self.{call}")
        except Exception as e:
            results = f"Error: Failed to run {call}: {e}"
        return results

    def get_endpoint_list(self, commands):
        """
        Returns a string-notation formatted endpoint string of commands list
        """
        # strip unrelated items from list
        for c in ['api', 'get', 'post', 'put']:
            if c in commands:
                commands.remove(c)
        return commands

    def _get_vmid(self, level_list):
        """
        Returns the vmid from the given level_list
        """
        return level_list[level_list.index("vm") + 1]

    def _get_vmid_node(self, vmid):
        """
        Returns the node of the given vmid
        """
        return [vm['node'] for vm in self.get_vms() if f"{vm.get('vmid')}" == vmid][0]

### TUAH HANDLER FUNCS BELOW THIS LINE ###

    def clone_vm(self, level_list=[], params=[]):
        """
        Clones a vm with requested params
        """

        match scope.lower():
            case "brief":
                return self.get_vms_brief()
            case "detail":
                return self.get_vms()
            case "config":
                return "TO BE IMPLEMENTED"

    def connect_vm(self, level_list=[], params=[]):
        """
        Wrapper to connect to specific VM
        """
        vmid = self._get_vmid(level_list)
        node = self._get_vmid_node(vmid)

        # get and write formatted spice file
        spice_conf = self.get_spice_config(vmid, node)
        filename = self.config.get('spice_file', 'tmp_spice.vv')

        try:
            with open(filename, "w") as f:
                f.write("[virt-viewer]\n")
                for k,v in spice_conf.items():
                    f.write(f"{k}={v}\n")
        except IOError as e:
            return f"Error: Failed to create spice file '{filename}': {e}"

        # open spice file with spice client
        try:
            spice_client = Path(self.config.get('spice_client_path', 'remote-viewer'))
            subprocess.Popen([str(spice_client), filename], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"Launched spice client"
        except Exception as e:
            return f"Error occurred launching spice client '{spice_client}': {e}"


    def show_vm(self, level_list=[], params=[]):
        """
        Wrapper to provide list of specific VM's info depending on received scope
        """
        vmid = self._get_vmid(level_list)

        scope = "brief"

        if params:
            scope = params[0]

        match scope.lower():
            case "brief":
                return [vm for vm in self.get_vms_brief() if f'{vm.get("vmid","")}' == vmid][0]
            case "detail":
                return [vm for vm in self.get_vms() if f'{vm.get("vmid","")}' == vmid][0]
            case "config":
                return "TO BE IMPLEMENTED"

    def show_vms(self, level_list=[], params=[]):
        """
        Wrapper to provide list of all VM info depending on received scope
        """
        scope = "brief"

        if params:
            scope = params[0]

        match scope.lower():
            case "brief":
                return self.get_vms_brief()
            case "detail":
                return self.get_vms()
            case "config":
                return "TO BE IMPLEMENTED"


    def rawdog(self, level_list=[], params=[]):
        """
        Accepts fully formatted function call and attempts to run it
        """
        call = params[0]

        try:
            results = eval(call)
        except Exception as e:
            results = f"Error: Failed to run {call}: {e}"
        return results

    def run_func(self, level_list=[], params=[]):
        # first item in params is param string
        full_string = "".join(params)

        # confirm function syntax
        if not re.search(r'\w+\(*\)$', full_string):
            self.print_error(f"Entered text '{full_string}' not formatted as function: <name>(<args>)")
            return

        # get func name and arg(s)
        func_name = full_string.split("(")[0]
        open_index = full_string.find("(")
        arg_string = full_string[open_index + 1:-1]
        arg_list = []
        if arg_string:
            arg_list = arg_string.split(",")

        # check if this is a ProxmoxHandler function
        if func_name in ProxmoxHandler.__dict__:
            if callable(ProxmoxHandler.__dict__[func_name]):
                func = getattr(self, func_name)

                try:
                    if arg_list:
                        results = func(*arg_list)
                    else:
                        results = func()
                except Exception as e:
                    results = f"Error: {e}"
        else:
            results = f"Error: Function {func_name} not found"

        return results

    def get(self, level_list=[], params=[]):
        """
        Executes api get call
        """
        # strip api/get from level_list
        level_list.remove('api')
        level_list.remove('get')

        # consolidate endpoints for string-notation call
        endpoint = "/".join(level_list)

        try:
            results = eval(f"self('{endpoint}').get()")
        except:
            results = (f"Error: failed to GET: {endpoint}")

        return results

    def post(self, level_list=[], params=[]):
        """
        Executes api post call where endpoint is derived from level_list and params from params
        """

        # get endpoint for string-notation call
        endpoint = "/".join(self.get_endpoint_list(level_list))

        # attempt api call
        try:
            if params:
                results = eval(f"self('{endpoint}').post({','.join(params)})")
            else:
                results = eval(f"self('{endpoint}').post()")
        except Exception as e:
            if params:
                results = (f"Error: failed to POST '{endpoint}' with params '{params}' ({e})")
            else:
                results = (f"Error: failed to POST '{endpoint}' with no params ({e})")

        return results

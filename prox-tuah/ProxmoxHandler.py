import yaml
import re
import subprocess
import webbrowser
from proxmoxer import ProxmoxAPI
from pprint import pprint
from pathlib import Path

class ProxmoxHandler(ProxmoxAPI):
    """
    Interface for interacting with Proxmox API
    """
    def __init__(self, config_path='config.yaml', **kwargs):
        self.config = self.load_config(config_path)
        self.api_doc_root = "https://pve.proxmox.com/pve-docs/api-viewer/index.html#/"

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


### VM ###
    def _get_vms(self):
        return [vm for vm in self.cluster.resources.get() if vm.get('type') == 'qemu' and vm.get('template') == 0]


    def _get_vms_dict(self):
        vms = {}
        for vm in self._get_vms():
            vms.update({str(vm['vmid']): vm})
        return vms

    def _get_vm(self, vmid):
        return self._get_vms_dict().get(vmid)

    def _get_vm_keyvalue(self, vmid, key):
        return {key: self._get_vm(vmid).get(key,"N/A")}


    def _get_vms_name_list(self, *args, **kwargs):
        return [{vm['vmid']: vm['name']} for vm in self._get_vms()]

    def _get_vms_brief(self):
        return [{'vmid': vm['vmid'], 'name': vm['name'], 'node': vm['node'], 'status': vm['status']} for vm in self._get_vms()]

### NODE ###
    def _get_nodes(self):
        return [vm for vm in self.cluster.resources.get() if vm.get('type') == 'node']

    def _get_nodes_brief(self):
        return [{'node': node['node'], 'status': node['status']} for node in self._get_nodes()]

    def _get_node(self, node):
        return [n for n in self._get_nodes() if node.get('node') == node][0]

    def _get_node_names(self):
        return [n['node'] for n in self._get_nodes()]

    def _get_node_storage(self, node):
        return self.nodes(node).storage.get()

    def _get_node_storage_names(self, node):
        return [s['storage'] for s in self.nodes(node).storage.get()]

### ISO ###
    def _get_isos(self):
        isos = []
        for node in self._get_node_names():
            for s in self._get_node_storage_names(node):
                storage_isos = self.nodes(node).storage(s).content.get(content="iso")
                if storage_isos:
                    isos.extend(storage_isos)
        return isos

    def _get_isos_brief(self):
        isos = []
        for iso in self._get_isos():
            iso_dict = {}
            volid = iso["volid"]
            name = volid.split("iso/")[1]
            iso_dict.update({"name": name})
            isos.append(iso_dict)
        return isos

### TEMPLATE ###
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
        for c in ['api', 'get', 'post', 'put', 'delete']:
            if c in commands:
                commands.remove(c)
        return commands

    def _get_docs_endpoint_list(self, commands):
        """
        Returns a string-notation formatted endpoint string of commands list
        """
        # Dict map of variable parents to variable name
        var_map = {
            "account": "name",
            "aliases": "name",
            "backup": "id",
            "content": "volume",
            "controllers": "controller",
            "dir": "id",
            "directory": "name",
            "dns": "name",
            "domains": "realm",
            "fabric": "id",
            "fabrics": "fabric",
            "flags": "flag",
            "fs": "name",
            "gotify": "name",
            "groups": "group",
            "ipams": "ipam",
            "ipset": "name",
            "lvmthin": "name",
            "lxc": "vmid",
            "matchers": "name",
            "mds": "name",
            "mgr": "name",
            "mon": "monid",
            "network": "iface",
            "node": "fabric_id",
            "nodes": "node",
            "osd": "osdid",
            "pci": "pci-id-or-mapping",
            "pool": "name",
            "pools": "poolid",
            "plugins": "id",
            "qemu": "vmid",
            "realm-sync": "id",
            "replication": "id",
            "resources": "sid",
            "rules": "pos", # conflicting child, see edge case below
            "roles": "roleid",
            "sendmail": "name",
            "services": "service",
            "server": "id",
            "smtp": "name",
            "snapshot": "snapname",
            "storage": "storage",
            "subnets": "subnet",
            "tasks": "upid",
            "targets": "name",
            "token": "tokenid",
            "tfa": "userid",
            "users": "userid",
            "vnets": "vnet",
            "webhook": "name",
            "zfs": "name",
            "zones": "zone",
        }
        # strip unrelated items from list
        for c in ['api', 'get', 'post', 'put', 'delete', 'docs']:
            if c in commands:
                commands.remove(c)

        # substition loop skip control
        skip_next = False

        # perform substitutions at levels that are vars in API
        for i, level in enumerate(commands):
            if skip_next:
                skip_next = False
            else:
                if level in var_map.keys() and i+1 < len(commands):
                    commands[i+1] = f"{{{var_map[level]}}}"
                    skip_next = True

                    # edge cases for subsequent vars
                    if level == "tfa" and i+2 < len(commands):
                        commands[i+2] = f"{{id}}"
                    elif level == "groups" and i+2 < len(commands):
                        commands[i+2] = f"{{pos}}"
                    elif level == "ipset" and i+2 < len(commands):
                        commands[i+2] = f"{{cidr}}"
                    elif level == "ipset" and i+2 < len(commands):
                        commands[i+2] = f"{{cidr}}"
                    elif level == "node" and commands[i-1] == "fabrics" and i+2 < len(commands):
                        commands[i+2] = f"{{node_id}}"

                    # edge cases for conflicting var children
                    if level == "rules" and i+1 < len(commands) and commands[i-1] == "ha":
                        commands[i+1] = f"{{rule}}"
                    elif level == "pci" and i+1 < len(commands) and commands[i-1] == "mapping":
                        commands[i+1] = f"{{id}}"
        return commands

### PARAM HANDLING ###
    def _get_vmid(self, level_list):
        """
        Returns the vmid from the given level_list
        """
        return level_list[level_list.index("vm") + 1]

    def _get_vmid_node(self, vmid):
        """
        Returns the node of the given vmid
        """
        return [vm['node'] for vm in self._get_vms() if f"{vm.get('vmid')}" == vmid][0]

    def _get_kwargs_dict(self, params):
        """
        Returns dict of converted kwarg params list, stripping redundant string quotes
        """

        params_dict = {}
        for p in params:
            k,v = p.split("=")
            if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                params_dict[k] = v[1:-1]
            else:
                params_dict[k] = v

        return params_dict

    def _get_kwargs_str(self, params):
        """
        Returns formatted string of kwargs from given params list, adding quotes to values
        """
        params_dict = self._get_kwargs_dict(params)

        kwargs_list = []
        for k,v in params_dict.items():
            kwargs_list.append(f'{k}="{v}"')

        return ",".join(kwargs_list)

### TUAH HANDLER FUNCS BELOW THIS LINE ###
    def show_vm_info(self, level_list=[], params=[]):
        """
        Show vm's info at requested level
        """
        vmid = self._get_vmid(level_list)
        node = self._get_vmid_node(vmid)

        # accept first param, if any as scope
        if params:
            scope = params[0]
        else:
            scope = "default"

        try:
            match scope:
                case "brief":
                    output =  [vm for vm in self._get_vms_brief() if f'{vm.get("vmid","")}' == vmid][0]
                case "default":
                    output = self._get_vm(vmid)
                case "power":
                    output = self._get_vm_keyvalue(vmid, "status")
                case _:
                    output = self._get_vm(vmid)
        except Exception as e:
            output = f"ERROR: Unable to get status of '{vmid}' on '{node}': {e}"

        return output

    def change_vm_status(self, level_list=[], params=[]):
        """
        Change vm's power status
        """
        vmid = self._get_vmid(level_list)
        node = self._get_vmid_node(vmid)

        if params:
            new_status = params[0]
        else:
            return "ERROR: Missing required parameter: <action>"

        if new_status in ["reboot", "reset", "resume", "shutdown", "start", "stop", "suspend"]:
            try:
                match new_status:
                    case "reboot":
                        output = self.nodes(node).qemu(vmid).status.reboot.create()
                    case "reset":
                        output = self.nodes(node).qemu(vmid).status.reset.create()
                    case "resume":
                        output = self.nodes(node).qemu(vmid).status.resume.create()
                    case "shutdown":
                        output = self.nodes(node).qemu(vmid).status.shutdown.create()
                    case "start":
                        output = self.nodes(node).qemu(vmid).status.start.create()
                    case "stop":
                        output = self.nodes(node).qemu(vmid).status.stop.create()
                    case "suspend":
                        output = self.nodes(node).qemu(vmid).status.suspend.create()
            except Exception as e:
                output = f"ERROR: Unable to change power state of '{vmid}' on '{node}': {e}"
        else:
            output = f"ERROR: Unknown status '{new_status}'"

        return output

    def clone_vm(self, level_list=[], params=[]):
        """
        Clones a vm with requested params
        """
        vmid = self._get_vmid(level_list)
        node = self._get_vmid_node(vmid)

        params_dict = self._get_kwargs_dict(params)

        return self.nodes(node).qemu(vmid).clone.create(**params_dict)

    def edit_vm(self, level_list=[], params=[]):
        """
        Edits a vm with requested params
        """
        vmid = self._get_vmid(level_list)
        node = self._get_vmid_node(vmid)

        # package list of kwargs as dict for unpacking
        params_dict = {}
        for p in params:
            k,v = p.split("=")
            params_dict[k] = v

        try:
            output = self.nodes(node).qemu(vmid).config.create(**params_dict)
        except Exception as e:
            output = f"Error deleting VM {vmid}: {e}"

        return output

    def delete_vm(self, level_list=[], params=[]):
        """
        Deletes VM
        """
        vmid = self._get_vmid(level_list)
        node = self._get_vmid_node(vmid)

        # package list of kwargs as dict for unpacking

        try:
            output = self.nodes(node).qemu(vmid).delete()
        except Exception as e:
            output = f"ERROR: Failed to delete VM {vmid}: {e}"

        return output

    def connect_vm(self, level_list=[], params=[]):
        """
        Wrapper to connect to specific VM
        """
        vmid = self._get_vmid(level_list)
        node = self._get_vmid_node(vmid)

        # get and write formatted spice file
        try:
            spice_conf = self.get_spice_config(vmid, node)
            filename = self.config.get('spice_file', 'tmp_spice.vv')
        except Exception as e:
            return f"ERROR: Failed to pull spice config for VM {vmid}\n({e})"

        try:
            with open(filename, "w") as f:
                f.write("[virt-viewer]\n")
                for k,v in spice_conf.items():
                    f.write(f"{k}={v}\n")
        except IOError as e:
            return f"ERROR: Failed to create spice file '{filename}'\n({e})"

        # open spice file with spice client
        try:
            spice_client = Path(self.config.get('spice_client_path', 'remote-viewer'))
            subprocess.Popen([str(spice_client), filename], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"Launched spice client"
        except Exception as e:
            return f"ERROR: Unable to launch spice client '{spice_client}'\n({e})"


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
                return [vm for vm in self._get_vms_brief() if f'{vm.get("vmid","")}' == vmid][0]
            case "detail":
                return [vm for vm in self._get_vms() if f'{vm.get("vmid","")}' == vmid][0]
            case "config":
                return "TO BE IMPLEMENTED"

    def list_nodes(self, level_list=[], params=[]):
        """
        Wrapper to provide list of all nodes info depending on received scope
        """
        scope = "brief"

        if params:
            scope = params[0]

        match scope.lower():
            case "brief":
                return self._get_nodes_brief()
            case "detail":
                return self._get_nodes()
            case "config":
                return "TO BE IMPLEMENTED"

    def list_isos(self, level_list=[], params=[]):
        """
        Wrapper to provide list of all iso info depending on received scope
        """
        scope = "brief"

        if params:
            scope = params[0]

        match scope.lower():
            case "brief":
                return self._get_isos_brief()
            case "detail":
                return self._get_isos()

    def show_vms(self, level_list=[], params=[]):
        """
        Wrapper to provide list of all VM info depending on received scope
        """
        scope = "brief"

        if params:
            scope = params[0]

        match scope.lower():
            case "brief":
                return self._get_vms_brief()
            case "detail":
                return self._get_vms()
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
        # strip api/get from level_list, if present
        if "api" in level_list:
            level_list.remove('api')
        level_list.remove('get')

        # consolidate endpoints for string-notation call
        endpoint = "/".join(level_list)

        kwargs_str = self._get_kwargs_str(params)

        try:
            if kwargs_str:
                results = eval(f"self('{endpoint}').get({kwargs_str})")
            else:
                results = eval(f"self('{endpoint}').get()")
        except Exception as e:
            if kwargs_str:
                results = (f"Error: failed to GET '{endpoint}' with params '{kwargs_str}' ({e})")
            else:
                results = (f"Error: failed to GET '{endpoint}' with no params ({e})")

        return results

    def post(self, level_list=[], params=[]):
        """
        Executes api post call where endpoint is derived from level_list and params from params
        """

        # get endpoint for string-notation call
        endpoint = "/".join(self.get_endpoint_list(level_list))

        kwargs_str = self._get_kwargs_str(params)

        # attempt api call
        try:
            if kwargs_str:
                results = eval(f"self('{endpoint}').post({kwargs_str})")
            else:
                results = eval(f"self('{endpoint}').post()")
        except Exception as e:
            if kwargs_str:
                results = (f"Error: failed to POST '{endpoint}' with params '{kwargs_str}' ({e})")
            else:
                results = (f"Error: failed to POST '{endpoint}' with no params ({e})")

        return results

    def put(self, level_list=[], params=[]):
        """
        Executes api put call where endpoint is derived from level_list and params from params
        """

        # get endpoint for string-notation call
        endpoint = "/".join(self.get_endpoint_list(level_list))

        kwargs_str = self._get_kwargs_str(params)

        # attempt api call
        try:
            if kwargs_str:
                results = eval(f"self('{endpoint}').put({kwargs_str})")
            else:
                results = eval(f"self('{endpoint}').put()")
        except Exception as e:
            if kwargs_str:
                results = (f"Error: failed to PUT '{endpoint}' with params '{kwargs_str}' ({e})")
            else:
                results = (f"Error: failed to PUT '{endpoint}' with no params ({e})")

        return results

    def delete(self, level_list=[], params=[]):
        """
        Executes api delete call where endpoint is derived from level_list and params from params
        """

        # get endpoint for string-notation call
        endpoint = "/".join(self.get_endpoint_list(level_list))

        kwargs_str = self._get_kwargs_str(params)

        # attempt api call
        try:
            if kwargs_str:
                results = eval(f"self('{endpoint}').delete({kwargs_str})")
            else:
                results = eval(f"self('{endpoint}').delete()")
        except Exception as e:
            if kwargs_str:
                results = (f"Error: failed to delete '{endpoint}' with params '{kwargs_str}' ({e})")
            else:
                results = (f"Error: failed to delete '{endpoint}' with no params ({e})")

        return results

    def docs(self, level_list=[], params=[]):
        """
        Opens web browser to PVE API documentation of specified endpoint
        """

        # get endpoint for string-notation call
        endpoint = "/".join(self._get_docs_endpoint_list(level_list))

        f_url = self.api_doc_root + endpoint

        # attempt api call
        try:
            webbrowser.open(f_url)
            results = f"Opening web browser to PVE API endpoint documentation: {f_url}"
        except Exception as e:
            results = (f"Error: Unable to open web browser to docs at '{endpoint}' - ({e})")

        return results

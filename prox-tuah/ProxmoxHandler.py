import yaml
import re
import subprocess
import webbrowser
import random
from proxmoxer import ProxmoxAPI
from pprint import pprint
from pathlib import Path
from tabulate import tabulate
from textwrap import indent

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


### VM/TEMPLATE ###
    def _get_vms(self, template=False):
        if template:
            return [vm for vm in self.cluster.resources.get() if vm.get('type') == 'qemu' and vm.get('template') == 1]
        else:
            return [vm for vm in self.cluster.resources.get() if vm.get('type') == 'qemu' and vm.get('template') == 0]


    def _get_vms_dict(self, template=False):
        vms = {}
        for vm in self._get_vms(template=template):
            vms.update({str(vm['vmid']): vm})
        return vms

    def _get_vm(self, vmid, template=False):
        return self._get_vms_dict(template=template).get(vmid)

    def _get_vm_keyvalue(self, vmid, key, template=False):
        return {key: self._get_vm(vmid, template=template).get(key,"N/A")}


    def _get_vms_name_list(self, *args, **kwargs):
        return [{vm['vmid']: vm['name']} for vm in self._get_vms()]

    def _get_vmids_names_string(self, node="all", *args, **kwargs):
        """Returns a list of strings containing vmid and vm name"""
        if node == "all":
            return [f"{vm['vmid']} ({vm['name']})" for vm in self._get_vms()]
        else:
            return [f"{vm['vmid']} ({vm['name']})" for vm in self._get_vms() if vm['node'] == node]

    def _get_vmids(self, node="all", *args, **kwargs):
        """Returns a list of vmids"""
        if node == "all":
            return [str(vm['vmid']) for vm in self._get_vms()]
        else:
            return [str(vm['vmid']) for vm in self._get_vms() if vm['node'] == node]

    def _get_vms_brief(self, template=False):
        return [{'vmid': vm['vmid'], 'name': vm['name'], 'node': vm['node'], 'status': vm['status']} for vm in self._get_vms(template=template)]

    def _delete_vm(self, vmid, template=False):
        vm = self._get_vm(vmid, template=template)
        node = vm["node"]
        return self.nodes(node).qemu(vmid).delete()

### NODE ###
    def _get_nodes(self):
        return [vm for vm in self.cluster.resources.get() if vm.get('type') == 'node']

    def _get_nodes_brief(self):
        return [{'node': node['node'], 'status': node['status']} for node in self._get_nodes()]

    def _get_node(self, node):
        return [n for n in self._get_nodes() if node.get('node') == node][0]

    def _get_node_names(self, *args, **kwargs):
        return [n['node'] for n in self._get_nodes()]

    def _get_node_storage(self, node):
        return self.nodes(node).storage.get()

    def _get_node_storage_names(self, node):
        return [s['storage'] for s in self.nodes(node).storage.get()]

### ISO ###
    def _get_isos(self):
        """Returns all ISOs"""
        isos = []
        for node in self._get_node_names():
            storage_isos = self._get_node_isos(node)
            if storage_isos:
                isos.extend(storage_isos)
        return isos

    def _get_iso(self, name):
        """Returns named ISO including residing node/storage"""
        storages = self._get_iso_storages()
        for s in storages:
            isos = self._get_node_isos(s["node"])
            if isos:
                for i in isos:
                    if i["volid"].endswith(f"/{name}"):
                        iso = i
                        iso.update({"node": s["node"], "storage": s["storage"]})
                        return iso

    def _get_node_isos(self, node):
        """Return ISOs on given node"""
        isos = []
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

    def _get_iso_storages(self):
        storages = []
        for storage in self.cluster.resources.get(type="storage"):
            if "iso" in storage["content"]:
                storages.append({"storage": storage["storage"], "node": storage["node"]})
        return storages

### TEMPLATE ###
    def get_templates_list(self):
        return [vm for vm in self.cluster.resources.get() if vm.get('type') == 'qemu' and vm.get('template') == 1]

    def get_templates_name_list(self):
        return [{vm['vmid']: vm['name']} for vm in self.get_templates_list()]

### NETWORK ###
    def _get_networks(self):
        """Returns list of networks including node per-network"""
        nodes = self._get_node_names()
        networks = []
        for node in nodes:
            nets = self._get_node_networks(node)

            # add node name to nets dict
            for n in nets:
                n['node'] = node

            # add node's nets to networks list
            networks.extend(nets)

        return networks

    def _get_networks_brief(self):
        nets = self._get_networks()

        networks = []

        # pull desired values for brief output
        for net in nets:
            n = {}
            for k in ["node", "iface", "type", "active", "cidr"]:
                n.update({k: net.get(k, '')})
            networks.append(n)

        return networks

    def _get_ifaces(self, node="all", *args, **kwargs):
        """Returns a list of ifaces"""
        if node == "all":
            return [net['iface'] for net in self._get_networks()]
        else:
            return [net['iface'] for net in self._get_networks() if net['node'] == node]


    def _get_node_networks(self, node):
        return self.nodes(node).network.get()

### POOL ###
    def _get_pools(self):
        """Returns dict of pools"""
        return self._order_dict_list(self.pools.get(), ["poolid", "comment"])

    def _get_pools_members(self):
        """Returns list of pool dicts, including their members"""
        f_pools = []
        pools = self._get_pools()
        for pool in pools:
            name = pool['poolid']
            members = self._get_pool_members(name)
            pool.update({"members": "\n".join(members)})
            f_pools.append(pool)

        return f_pools

    def _get_pool_members(self, pool):
        """Returns list of member names of specified pool"""
        members = self.pools(pool).get()["members"]

        return [f"({m['vmid']}) {m['name']}" for m in members]

### UTILITY ###
    def _get_syntax_block(self, method="get", endpoint="", kwargs_str=""):
        """Returns a formatted string block of api syntaxes for given method/endpoint/kwargs and api_syntaxes in config"""
        syntax_list = []
        for s in self.config.get("api_syntax"):
            if s.lower() == "proxmoxer":
                call_string = f'ProxmoxAPI("{endpoint}").{method}({kwargs_str if kwargs_str else ""})'
                syntax_list.append({"API Caller": "proxmoxer", "Syntax": call_string})

            elif s.lower() == "pvesh":
                params = []
                # split out kwarg_str into individual params
                if kwargs_str:
                    kwargs = kwargs_str.split(",")
                    for kwarg in kwargs:
                        k, s, v = kwarg.partition("=")
                        params.extend([f"--{k}", v])

                if method == "post":
                    method = "create"
                elif method == "put":
                    method = "set"
                if params:
                    call_string = f'pvesh {method} /{endpoint} {" ".join(params)}'
                else:
                    call_string = f'pvesh {method} /{endpoint}'

                syntax_list.append({"API Caller": "pvesh", "Syntax": call_string})
            elif s.lower() == "curl":
                params = []
                # split out kwarg_str into curl data params
                if kwargs_str:
                    kwargs = kwargs_str.split(",")
                    for kwarg in kwargs:
                        params.append(f"--data-urlencode {kwarg}")

                f_method = method.upper() if method != "get" else ""

                if params:
                    if f_method:
                        call_string = f'curl -k -H "Authorization: PVEAPIToken=<token>" -X {f_method} {f" ".join(params)} https://{self.config.get("server", "<server_ip>")}:8006/api2/json/{endpoint}'
                    else:
                        call_string = f'curl -k -H "Authorization: PVEAPIToken=<token>" {f" ".join(params)} https://{self.config.get("server", "<server_ip>")}:8006/api2/json/{endpoint}'
                else:
                    if f_method:
                        call_string = f'curl -k -H "Authorization: PVEAPIToken=<token>" -X {f_method} https://{self.config.get("server", "<server_ip>")}:8006/api2/json/{endpoint}'
                    else:
                        call_string = f'curl -k -H "Authorization: PVEAPIToken=<token>" https://{self.config.get("server", "<server_ip>")}:8006/api2/json/{endpoint}'

                syntax_list.append({"API Caller": "curl", "Syntax": call_string})

        return tabulate(syntax_list, headers="keys")

    def _order_dict_list(self, unordered, order):
        """Returns a list of dicts with key/values ordered according to received order list"""
        ordered = []

        # order each dict item according to order list
        for u_dict in unordered:
            o_dict = {}
            for k in order:
                o_dict.update({k: u_dict.get(k, "N/A")})
            ordered.append(o_dict)

        return ordered

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
    def _get_vmid(self, level_list, template=False):
        """
        Returns the vmid from the given level_list
        """
        if template:
            return level_list[level_list.index("template") + 1]
        else:
            return level_list[level_list.index("vm") + 1]

    def _get_vmid_node(self, vmid, template=False):
        """
        Returns the node of the given vmid
        """
        return [vm['node'] for vm in self._get_vms(template=template) if f"{vm.get('vmid')}" == vmid][0]

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

### VM ###

    def show_vm_info(self, level_list=[], params=[], template=False):
        """
        Show vm's info at requested level
        """
        vmid = self._get_vmid(level_list, template=template)
        node = self._get_vmid_node(vmid, template=template)

        # accept first param, if any as scope
        if params:
            scope = params[0]
        else:
            scope = "default"

        try:
            match scope:
                case "brief":
                    output =  [vm for vm in self._get_vms_brief(template=template) if f'{vm.get("vmid","")}' == vmid][0]
                case "default":
                    output = self._get_vm(vmid, template=template)
                case "power":
                    output = self._get_vm_keyvalue(vmid, "status")
                case _:
                    output = self._get_vm(vmid, template=template)
        except Exception as e:
            output = f"ERROR: Unable to get information for '{vmid}' on '{node}': {e}"

        return output

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

    def get_vmids_names_string(self, level_list=[], params=[]):
        """
        Wrapper to provide list of vmids/names strings
        """
        if level_list[0] == "api":
            node = level_list[-2]
        else:
            node = "all"

        return self._get_vmids_names_string(node=node)

    def get_vmids(self, level_list=[], params=[]):
        """
        Wrapper to provide list of vmids
        """
        if level_list[0] == "api":
            node = level_list[-2]
        else:
            node = "all"

        return self._get_vmids(node=node)

    def validate_vmid(self, level_list=[], params=[]):
        """
        Validate whether specified vm exists
        """
        if level_list[0] == "api":
            node = level_list[-3]
        else:
            node = "all"

        vmid = level_list[-1]

        if vmid in self._get_vmids(node=node):
            return True
        else:
            return f"VM '{vmid}' is not valid"

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

    def clone_vm(self, level_list=[], params=[], template=False):
        """
        Clones a vm with requested params
        """
        vmid = self._get_vmid(level_list, template=template)
        node = self._get_vmid_node(vmid, template=template)

        params_dict = self._get_kwargs_dict(params)

        # use next available vmid if not provided
        if not params_dict.get("newid"):
            next_vmid = self.cluster.nextid.get()
            params_dict.update({"newid": next_vmid})

        return self.nodes(node).qemu(vmid).clone.create(**params_dict)

    def template_vm(self, level_list=[], params=[]):
        """
        Converts a vm to templatewith requested params
        """
        vmid = self._get_vmid(level_list)
        node = self._get_vmid_node(vmid)

        params_dict = self._get_kwargs_dict(params)

        return self.nodes(node).qemu(vmid).template.create(**params_dict)

    def edit_vm(self, level_list=[], params=[], template=False):
        """
        Edits a vm with requested params
        """
        vmid = self._get_vmid(level_list, template=template)
        node = self._get_vmid_node(vmid, template=template)

        # package list of kwargs as dict for unpacking
        params_dict = {}
        for p in params:
            k,v = p.split("=")
            params_dict[k] = v

        if template:
            v_type = "template"
        else:
            v_type = "VM"
        try:
            output = self.nodes(node).qemu(vmid).config.create(**params_dict)
        except Exception as e:
            output = f"ERROR: Unable to delete {v_type} {vmid}: {e}"

        return output

    def delete_vms(self, level_list=[], params=[], template=False):
        """
        Deletes VMs (from parent context)
        """
        if template:
            v_type = "template"
        else:
            v_type = "VM"

        # join multiple params into single string if csv separated by spaces
        p_string = "".join(params)

        # split csv params into individual vmids
        vmids = p_string.split(",")

        output = []

        # delete each VM
        for vmid in vmids:
            try:
                results = self._delete_vm(vmid, template=template)
                output.append(f"Deleting {v_type} {vmid} ({results})")
            except Exception as e:
                output.append(f"ERROR: Failed to delete {v_type} {vmid}: ({e})")

        return "\n".join(output)

    def delete_vm(self, level_list=[], params=[], template=False):
        """
        Deletes VM (from VM's context)
        """
        if template:
            v_type = "template"
        else:
            v_type = "VM"

        vmid = self._get_vmid(level_list, template=template)

        try:
            results = self._delete_vm(vmid, template=template)
            return f"Deleting {v_type} {vmid} ({results})"
        except Exception as e:
            return f"ERROR: Failed to delete {v_type} {vmid}: ({e})"

### TEMPLATE ###
    def show_templates(self, level_list=[], params=[]):
        """
        Wrapper to provide list of all VM info depending on received scope
        """
        scope = "brief"

        if params:
            scope = params[0]

        match scope.lower():
            case "brief":
                return self._get_vms_brief(template=True)
            case "detail":
                return self._get_vms(template=True)
            case "config":
                return "TO BE IMPLEMENTED"

    def show_template_info(self, level_list=[], params=[]):
        """
        Show vm's info at requested level
        """
        return self.show_vm_info(level_list=level_list, params=params, template=True)

    def edit_template(self, level_list=[], params=[], template=True):
        """
        Edits a vm with requested params
        """
        return self.edit_vm(level_list=level_list, params=params, template=True)

    def clone_template(self, level_list=[], params=[]):
        """
        Clones a template with requested params
        """
        return self.clone_vm(level_list=level_list, params=params, template=True)

    def delete_templates(self, level_list=[], params=[]):
        """
        Deletes templates (from parent context)
        """
        return self.delete_vms(level_list=level_list, params=params, template=True)

    def delete_template(self, level_list=[], params=[]):
        """
        Deletes template (from template's context)
        """
        return self.delete_vm(level_list=level_list, params=params, template=True)

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

### NODES ###
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

    def validate_node(self, level_list=[], params=[]):
        """
        Validate whether specified node is present
        """
        node = level_list[-1]

        if node in self._get_node_names():
            return True
        else:
            return f"Node '{node}' is not valid"

### ISO ###
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
            case "storage":
                return self._get_iso_storages()

    def delete_iso(self, level_list=[], params=[]):
        """
        Wrapper to delete iso
        """
        filename = params[0]

        # get iso details
        try:
            iso = self._get_iso(filename)
        except Exception as e:
            return f"ERROR: Unable to find ISO '{filename}'\n({e})"

        if not iso:
            return f"ERROR: Unable to find ISO '{filename}'"
        else:
            # delete iso
            try:
                results =  self.nodes(iso["node"]).storage(iso["storage"]).content(iso["volid"]).delete()
                return f"Deleting ISO '{filename}' on {iso['node']}/{iso['storage']}: ({results})"
            except Exception as e:
                return f"ERROR: Unable to delete ISO '{filename} on {iso['node']}/{iso['storage']}'\n({e})"

    def download_iso(self, level_list=[], params=[]):
        """
        Wrapper to download iso
        """
        params_dict = self._get_kwargs_dict(params)
        params_dict.update({"content": "iso"})
        storages = self._get_iso_storages()
        node = params_dict.pop("node", "")
        storage = params_dict.pop("storage", "")

        # get random storage on given node
        if node and not storage:
            n_storage = [s['storage'] for s in storages if s['node'] == node]
            storage = random.choices(n_storage)
        # get random node for given storage
        elif storage and not node:
            s_node = [s['node'] for s in storages if s['storage'] == storage]
            node = random.choices(s_node)
        # get random node and storage
        elif not node and not storage:
            r_storage = random.choice(storages)
            node = r_storage["node"]
            storage = r_storage["storage"]

        # check if given node/storage are valid iso stores
        is_valid = False
        for s in storages:
            if s["node"] == node and s["storage"] == storage:
               is_valid = True

        if is_valid:
            try:
                results = self.nodes(node).storage(storage)("download-url").post(**params_dict)
                return f"Downloading ISO '{params_dict['filename']}' to {node}/{storage}: ({results})"
            except Exception as e:
                return f"ERROR: Failed to download ISO {params_dict['filename']}: ({e})"
        else:
            return f"ERROR: Storage {node}/{storage} not found"

### NETWORKS ###
    def list_networks(self, level_list=[], params=[]):
        """
        Wrapper to provide list of networks depending on received scope
        """
        scope = "all"

        if params:
            scope = params[0]

        match scope.lower():
            case "brief":
                return self._get_networks_brief()
            case _:
                return self._get_networks()

    def add_network_device(self, level_list=[], params=[]):
        """
        Wrapper to add network device
        """
        params_dict = self._get_kwargs_dict(params)

        # get all nodes or specified node as list
        node = params_dict.pop("node", False)
        if not node:
            nodes = self._get_node_names()
        elif node.lower() != all:
            nodes = [node]
        else:
            nodes = self._get_node_names()

        results = []
        # add network to node(s)
        for n in nodes:
            try:
                upid = self.nodes(n).network.post(**params_dict)
                results.append(f"Adding network device {params_dict['iface']} to {n}")
            except Exception as e:
                results.append(f"ERROR: Failed to add network device to {n}: ({e})")

        return "\n".join(results)

    def reload_network(self, level_list=[], params=[]):
        """
        Wrapper to add reload network on node(s)
        """
        params_dict = self._get_kwargs_dict(params)

        # get all nodes or specified node as list
        node = params_dict.pop("node", False)
        if not node:
            nodes = self._get_node_names()
        elif node.lower() != all:
            nodes = [node]
        else:
            nodes = self._get_node_names()

        results = []
        # add network to node(s)
        for n in nodes:
            try:
                upid = self.nodes(n).network.put(node=n)
                results.append(f"Reloading network on {n}: {upid}")
            except Exception as e:
                results.append(f"ERROR: Failed to reload network on {n}: ({e})")

        return "\n".join(results)

    def remove_network_device(self, level_list=[], params=[]):
        """
        Wrapper to remove network device from node(s)
        """
        params_dict = self._get_kwargs_dict(params)
        iface = params_dict["iface"]

        # get all nodes or specified node as list
        node = params_dict.pop("node", False)
        if not node:
            nodes = self._get_node_names()
        elif node.lower() != all:
            nodes = [node]
        else:
            nodes = self._get_node_names()

        results = []
        # remove network from node(s)
        for n in nodes:
            try:
                upid = self.nodes(n).network(iface).delete()
                results.append(f"Removing network device {iface} from {n}")
            except Exception as e:
                results.append(f"ERROR: Failed to remove network device {iface} to {n}: ({e})")

        return "\n".join(results)

    def edit_network_device(self, level_list=[], params=[]):
        """
        Wrapper to edit network device on node(s)
        """
        params_dict = self._get_kwargs_dict(params)
        iface = params_dict.pop("iface")

        # get all nodes or specified node as list
        node = params_dict.pop("node", False)
        if not node:
            nodes = self._get_node_names()
        elif node.lower() != all:
            nodes = [node]
        else:
            nodes = self._get_node_names()

        results = []
        # edit network on node(s)
        for n in nodes:
            try:
                upid = self.nodes(n).network(iface).put(**params_dict)
                results.append(f"Updating network device {iface} on {n}: {upid}")
            except Exception as e:
                results.append(f"ERROR: Failed to edit network device {iface} on {n}")

        return "\n".join(results)

    def get_ifaces(self, level_list=[], params=[]):
        """
        Wrapper to provide list of networks
        """
        if level_list[0] == "api":
            node = level_list[-2]
        else:
            node = "all"

        return self._get_ifaces(node=node)

    def validate_iface(self, level_list=[], params=[]):
        """
        Validate whether specified vm exists
        """
        if level_list[0] == "api":
            node = level_list[-3]
        else:
            node = "all"

        iface = level_list[-1]

        if iface in self._get_ifaces(node=node):
            return True
        else:
            return f"Network interface '{iface}' is not valid"

### POOL ###
    def list_pools(self, level_list=[], params=[]):
        """
        Wrapper to provide list of pools
        """
        scope = "brief"

        if params:
            scope = params[0]

        match scope.lower():
            case "brief":
                return self._get_pools()
            case "detail":
                return self._get_pools_members()
            case _:
                return self._get_pools()

    def create_pool(self, level_list=[], params=[]):
        """
        Wrapper to create new pool
        """
        params_dict = self._get_kwargs_dict(params)
        poolid = params_dict.pop("name", False)
        params_dict.update({"poolid": poolid})

        results = []
        try:
            self.pools.post(**params_dict)
            results.append(f"Creating pool '{poolid}'")
        except Exception as e:
            results.append(f"ERROR: Failed to create pool '{poolid}': ({e})")

        return "\n".join(results)

    def delete_pool(self, level_list=[], params=[]):
        """
        Wrapper to delete pool
        """
        params_dict = self._get_kwargs_dict(params)
        poolid = params_dict.pop("name", False)
        params_dict.update({"poolid": poolid})

        results = []
        try:
            self.pools.delete(poolid=poolid)
            results.append(f"Deleting pool '{poolid}'")
        except Exception as e:
            results.append(f"ERROR: Failed to delete pool '{poolid}': ({e})")

        return "\n".join(results)

    def add_pool_members(self, level_list=[], params=[]):
        """
        Wrapper to add members to pool
        """
        params_dict = self._get_kwargs_dict(params)
        poolid = params_dict.pop("pool")
        params_dict.update({"poolid": poolid})
        vms_list = params_dict.pop("vms").split(",")
        params_dict.update({"allow-move": 1})

        results = []
        for vm in vms_list:
            try:
                kwargs_dict = params_dict.copy()
                kwargs_dict.update({"vms": vm})
                self.pools.put(**kwargs_dict)
                results.append(f"Adding VM '{vm}' to pool '{poolid}'")
            except Exception as e:
                results.append(f"ERROR: Failed to add VM '{vm}' to pool '{poolid}': ({e})")

        return "\n".join(results)

    def remove_pool_members(self, level_list=[], params=[]):
        """
        Wrapper to remove members from pool
        """
        params_dict = self._get_kwargs_dict(params)
        poolid = params_dict.pop("pool")
        params_dict.update({"poolid": poolid})
        vms_list = params_dict.pop("vms").split(",")
        params_dict.update({"allow-move": 1})
        params_dict.update({"delete": 1})

        results = []
        for vm in vms_list:
            try:
                kwargs_dict = params_dict.copy()
                kwargs_dict.update({"vms": vm})
                self.pools.put(**kwargs_dict)
                results.append(f"Removing VM '{vm}' from pool '{poolid}'")
            except Exception as e:
                results.append(f"ERROR: Failed to remove VM '{vm}' from pool '{poolid}': ({e})")

        return "\n".join(results)

### DEV ###
    def rawdog(self, level_list=[], params=[]):
        """
        Accepts fully formatted function call (including 'self' reference) and attempts to run it
        """
        call = params[0]

        try:
            results = eval(call)
        except Exception as e:
            results = f"Error: Failed to run {call}: {e}"
        return results

    def run_func(self, level_list=[], params=[]):
        """
        Accepts a fully formated function call (excluding 'self' reference) and attempts to run it
        """
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

### API ###
    def get(self, level_list=[], params=[]):
        """
        Executes api get call
        """
        # get endpoint for string-notation call
        endpoint = "/".join(self.get_endpoint_list(level_list))

        kwargs_str = self._get_kwargs_str(params)

        if self.config.get("api_syntax"):
            print(f'\n  --API SYNTAX--\n\n  {indent(self._get_syntax_block(method="get", endpoint=endpoint, kwargs_str=kwargs_str), "  ")}')
            print("\n  --CALL RESULTS--")

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

        if self.config.get("api_syntax"):
            print(f'\n  --API SYNTAX--\n\n  {indent(self._get_syntax_block(method="post", endpoint=endpoint, kwargs_str=kwargs_str), "  ")}')
            print("\n  --CALL RESULTS--")

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

        if self.config.get("api_syntax"):
            print(f'\n  --API SYNTAX--\n\n  {indent(self._get_syntax_block(method="put", endpoint=endpoint, kwargs_str=kwargs_str), "  ")}')
            print("\n  --CALL RESULTS--")

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

        if self.config.get("api_syntax"):
            print(f'\n  --API SYNTAX--\n\n  {indent(self._get_syntax_block(method="delete", endpoint=endpoint, kwargs_str=kwargs_str), "  ")}')
            print("\n  --CALL RESULTS--")

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
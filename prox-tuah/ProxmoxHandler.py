import yaml
from proxmoxer import ProxmoxAPI
from pprint import pprint

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

    def get_vms_list(self):
        return [vm for vm in self.cluster.resources.get() if vm.get('type') == 'qemu' and vm.get('template') == 0]

    def get_vms_dict(self):
        vms = {}
        for vm in self.get_vms_list():
            vms.update({str(vm['vmid']): vm})
        return vms

    def get_vm(self, vmid):
        return self.get_vms_dict().get(vmid) 

    def get_vms_name_list(self):
        return [{vm['vmid']: vm['name']} for vm in self.get_vms_list()]

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

    def rawdog(self, call):
        """
        Accepts fully formatted function call and attempts to run it
        """
        try:
            results = eval(call)
        except Exception as e:
            results = f"Error: Failed to run {call}: {e}"
        return results


    def print_func(self, func_name, *args):
        try:
            func = getattr(self, func_name)
        except:
            print(f"Error: Function {func_name} not found")
            return
        if args:
            print(func(*args))
        else:
            print(func())

    def run_func(self, func_name, *args, **kwargs):
        # check if this is a ProxmoxHandler function
        if func_name in ProxmoxHandler.__dict__:
            if callable(ProxmoxHandler.__dict__[func_name]):
                func = getattr(self, func_name)
                
                try:
                    results = func(*args, **kwargs)
                except Exception as e:
                    results = f"Error: {e}"
        else:
            results = f"Error: Function {func_name} not found"

#        try:
#            func = getattr(self, func_name)
#        except:
#            results = f"Error: Function {func_name} not found"
#            return results
#        
#        if args:
#            results = func(*args)
#        else:
#            results = func()

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
    
    def get(self, commands, **kwargs):
        """
        Executes api get call 
        """
        # strip api/get from command list
        commands.remove('api') 
        commands.remove('get') 

        # consolidate endpoints for string-notation call
        endpoint = "/".join(commands)
        
        try:
            results = eval(f"self('{endpoint}').get()")
        except:
            results = (f"Error: failed to GET: {endpoint}")
        
        return results
    
    def post(self, commands, **kwargs):
        """
        Executes api post call
        """

        params = kwargs.get('params')        

        # get endpoint for string-notation call
        endpoint = "/".join(self.get_endpoint_list(commands))

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

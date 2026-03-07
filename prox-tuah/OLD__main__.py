
import sys
import yaml
from TUAH import TUAH
from proxmoxer import ProxmoxAPI
from VMContext import VMMainContext
from ProxmoxInterface import ProxmoxInterface

class MainContext(TUAH):
    """"
    Main Context 
    """
    def __init__(self, pm):
        super().__init__()
        self.prompt = "Main# "
        self.intro = "Type 'help' to list commands, or 'help <command>' for command help\n"
        self.pm = pm
        try:
            with open('context.yaml','r') as file:
                self.context = yaml.safe_load(file)
        except FileNotFoundError:
            print("context.yaml not found")
            self.context = {}
        except yaml.YAMLError as e:
            print(f"Error parsing YAML file: {e}")
            self.context = {}
        

    def do_vm(self, argline):
        """
        Switch to VM context
        """
        if argline:
            print(f"Execute {argline}")
        else:
            VMMainContext(self.pm).cmdloop()

    def do_api(self, argline):
        """
        Switch to API context
        """
        APIContext(self.pm, self.context).cmdloop()
    
    def do_quit(self, argline):
        """
        Exit application
        """
        sys.exit(0) 

    def do_rawdog(self, argline):
        """
        Executes API call given as raw string 
        """
        self.pm.rawdog(argline.split()[0])

    def do_func(self, argline):
        """
        Prints return value of given ProxmoxInterface function
        """
        func_name = argline.split('(')[0]
        remainder = argline.split('(')[1]
        
        args = remainder.split(')')[0]

        if args:
            args = args.split(',')

        self.pm.print_func(func_name, args)

if __name__ == "__main__":
    pm = ProxmoxInterface()

    MainContext(pm).cmdloop()
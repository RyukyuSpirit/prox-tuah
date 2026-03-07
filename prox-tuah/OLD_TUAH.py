import sys
from cmd import Cmd
from inspect import cleandoc


class TUAH(Cmd):
    """
    Text-based user and administration hub context
    """
    def __init__(self):
        super().__init__()

    def print_topics(self, header, cmds, cmdlen, maxcol):
        """
        Displays available topics for this context
        """
        if cmds:
            # get length of longest cmd name for formatting
            max_length = 1
            for c in cmds:
                if len(c) > max_length:
                    max_length = len(c)

            global_cmds = []
            context_cmds = []
            for c in cmds:
                doc=""
                try:
                    doc=getattr(self, 'do_' + c).__doc__
                    doc = cleandoc(doc)
                        
                except AttributeError:
                    doc = "Undocumented"
                print(f"Func {c} is defined in")
                self.stdout.write(f"  {c.ljust(max_length + 5)}{doc} \n")
            self.stdout.write("\n")


    def emptyline(self):
        pass
    
    def do_exit(self, argline):
        """
        Exit current context
        """
        return True

    def do_quit(self, argline):
        """
        Close application
        """
        sys.exit(0)

        
import cmd

class BasicShell(cmd.Cmd):
    """
    somthin
    """

    def do_greet(self, argline):
        """
        Something
        """
        if argline:
            print(f"Hello, {argline}!")
        else:
            print("Hello, stranger")

    def do_bye(self, argline):
        """
        Docstring for do_bye
        
        :param self: Description
        :param argline: Description
        """
        print("Bye!")
        return True

if __name__ == "__main__":
    BasicShell().cmdloop()
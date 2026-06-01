import os
import sys
import colorama
import re
import fnmatch
import time
from prompt_toolkit import PromptSession
from prompt_toolkit.application.current import get_app
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.history import InMemoryHistory
from pprint import pprint
from tabulate import tabulate
from textwrap import indent


class TUAH():
    """
    text-based user and administration handler. Allows user to enter commands using the handler, and provides options based on the context.
    """

    def __init__(self, handler, context):
        self.handler = handler # handler object
        self.full_context = context # dictionary of application context(s)
        self.context = context # context at current level
        self.script_file = None
        self.global_help = {
            "exit": "Go back one context",
            "history": "View history",
            "sleep <secs>": "Sleep for <secs> seconds (useful for non-interactive scripts)",
            "top": "Return to top or execute from top (if followed by commands)",
            "quit": "Quit application",
            "..": "Go back one context or execute from previous context, if followed by '/' and commands (Nestable. Ex. '../../nodes get')",
        }
        self.pipe_context = {
            "pipe_params": {
                "fields":
                    {"description": "Return only values of comma-separated fields, if applicable (Ex. name,description)"},
                "filter":
                    {"description": "Return only matches of filter (Ex. user0*)"},
                "format":
                    {"description": "Return format format (Options: raw, table, or pretty)"},
            }

        }
        self.level_list = [] # list of keys to get to context
        self.prompt = "main# " # displayed prompt text
        logo = r"""
                           _               _
  _ __  _ __ _____  __    | |_ _   _  __ _| |__
 | '_ \| '__/ _ \ \/ /____| __| | | |/ _` | '_ \
 | |_) | | | (_) >  <_____| |_| |_| | (_| | | | |
 | .__/|_|  \___/_/\_\     \__|\__,_|\__,_|_| |_|
 |_|
        """
        self.welcome = f"{logo}\nWelcome to prox-tuah. Enter commands, '?' for help, or 'quit' to exit application.\n"
        self.typed_text = "" # last text string typed into the prompt (even if 'enter' not pressed)
        self.entry = "" # last text string entered into the prompt
        self.history = InMemoryHistory()
        self.session = PromptSession(history=self.history) # The prompt session
        self.handle_help = False # should help be displayed before next prompt
        self.handle_tab = False # should tab press be handled before next prompt
        self.handle_clear_screen = False # should screen be cleared before next prompt
        self.retain_text = False # should typed_text be inserted into next prompt

### PROMPT_SESSION ###
        # add keybindings for prompt
        self.bindings = KeyBindings()
        @self.bindings.add('?')
        def _(event):
            self.handle_help = True
            self.save_text_and_exit(event)


        @self.bindings.add('tab')
        def _(event):
            self.handle_tab = True
            self.save_text_and_exit(event)

        @self.bindings.add('c-l')
        def _(event):
            self.handle_clear_screen = True
            self.save_text_and_exit(event)

        # initialize colorama for cross-platform ANSI escape codes support
        colorama.init()

    def save_text_and_exit(self, event):
        """
        Save typed text from current prompt and exit prompt
        """
        self.typed_text = get_app().current_buffer.text
        event.app.exit(exception=KeyboardInterrupt)

### SESSION ###
    def clear_screen(self):
        """
        clears the terminal screen but retains the scrollback buffer
        """
        # clears screen and moves cursor to top left
        sys.stdout.write('\033[H\033[2J')
        try:
            # moves cursor to bottom-left
            rows, columns = os.get_terminal_size()
            sys.stdout.write(f'\033[{rows};1H')

        except OSError:
            sys.stdout.write('\n' * 100)

        sys.stdout.flush()

    def start(self, interactive=True, command=None, command_file=None, script_file=None):
        """
        Starts the TUAH either interactively, by running defined command or command_file, or all
        """
        self.script_file = script_file

        if interactive:
            self.clear_screen()
            self.go_to_top()
        self.run(interactive=interactive, command=command, command_file=command_file)

    def run(self, interactive=True, command=None, command_file=None):
        commands = []
        if command:
            commands.append(command)

        if command_file:
            print("processing file")
            with open(command_file, "r") as file:
                for c in file:
                    if not c.startswith("#"):
                        commands.append(c)

        if interactive:
            print(f"{self.welcome}")

            if commands:
                for c in commands:
                    print(f"{self.prompt} {c}")
                    self.history.append_string(c.rstrip())
                    self.handle_entry(c)

            while True:
                try:
                    self.handle_events()

                    # create prompt pre-filled with typed text
                    if self.retain_text:
                        self.retain_text = False
                        self.entry = self.session.prompt(self.prompt, default=self.typed_text, key_bindings=self.bindings)
                    # create empty prompt
                    else:
                        self.entry = self.session.prompt(self.prompt, key_bindings=self.bindings)
                except(KeyboardInterrupt):
                    continue
                except(EOFError):
                    self.exit_session()
                    break

                self.handle_entry(self.entry)
        else:
            if commands:
                for c in commands:
                    print(f"{self.prompt} {c}")
                    self.history.append_string(c.rstrip())
                    self.handle_entry(c)

    def exit_session(self):
        """
        Exits interactive session
        """
        if self.script_file:
            output = f"Script file saved at: {self.script_file}\n"
        else:
            output = ""
        output += "Terminated session."
        self.handle_output(output)
        sys.exit()

### UTILITY ###
    def _get_history(self):
        return self.session.history.get_strings()

    def _get_matches(self, text, context, level_list=[]):
        """
        Returns list of matches of text in context {<child|action|param>: <description>})
        """
        matches = []

        for k,v in context.get('context',{}).items():
            # add dict to matches of match and it's description
            if k.startswith(text):
                matches.append({"name": k, "description": v.get("description")})

        for k,v in context.get("actions",{}).items():
            # add dict to matches of match and it's description
            if k.startswith(text):
                matches.append({"name": k, "description": v.get("description")})

        for k,v in context.get("params",{}).items():
            # add dict to matches of match and it's description
            if k.startswith(text) and not v.get("is_var"):
                # if partial variable, format name w/ var suffix
                if v.get("is_part_var"):
                    matches.append({"name": f'{k}<{v.get("var_suffix", "N")}>', "description": v.get("description")})
                # otherwise, add kwarg name as is
                else:
                    matches.append({"name": k, "description": v.get("description")})

        for k,v in context.get("pipe_params",{}).items():
            # add dict to matches of match and it's description
            if k.startswith(text):
                matches.append({"name": k, "description": v.get("description")})

        if context.get("options_func"):
            options = self.handler_func(self.handler, context.get("options_func"), level_list=level_list)

            for o in options:
                if o.startswith(text):
                    matches.append({"name": o, "description": f"*Queried option"})

        return matches

    def _get_required_params(self, action_context):
        """
        Returns list of required parameters from given action_context
        """
        req_params = []

        params = action_context.get("params", {})

        for k,v in params.items():
            if v.get('required'):
                if v.get('is_var'):
                    req_params.append(f"{k}_VAR")
                else:
                    req_params.append(k)

        return req_params

    def _get_help(self, context, level_list=[]):
        """
        Return dict of help
        """
        # update help
        help = {}
        help['context'] = {}
        help['actions'] = {}
        help['params'] = {}
        help['pipe_params'] = {}

        for k,v in context.items():
            if isinstance(v, dict):
                if k == "context":
                    for ck,cv in v.items():
                        if cv.get("description"):
                            if cv.get("is_var"):
                                help["context"].update({f'<{ck}>': cv.get("description")})
                            else:
                                help["context"].update({ck: cv.get("description")})
                    # if options_func is present, add options to contexts
                    options_func = context.get("options_display_func", context.get("options_func"))
                    if options_func:

                        options = self.handler_func(self.handler, options_func, level_list=level_list)

                        for o in sorted(options):
                            help["context"].update({o: "*Queried option"})
                elif k == "actions":
                    for ck,cv in v.items():
                        if cv.get("description"):
                            help["actions"].update({ck: cv.get("description")})
                elif k == "params":
                    for ck,cv in v.items():
                        # format field according to var type
                        if cv.get("description"):
                            if cv.get("is_var"):
                                key = f'<{ck}>'
                            elif cv.get("is_part_var"):
                                var_suffix = cv.get("var_suffix", "N")
                                key = f'{ck}<{var_suffix}>'
                            elif cv.get("is_fixed"):
                                key = ck
                            else:
                                key = f'{ck}='

                            # add prefix if required
                            if cv.get("required"):
                                description = f"[REQ] {cv.get('description', ck)}"
                            else:
                                description = cv.get("description", ck)

                            help["params"].update({key: description})

                elif k == "pipe_params":
                    for ck,cv in v.items():
                        if cv.get("description"):
                            help["pipe_params"].update({f'{ck}=': cv.get("description")})

        return help

    def _container_has_match(self, container, r_pattern):
        """
        Returns True if container's child contains a match
        """
        if isinstance(container, list):
            # return True if list child contains match
            for i in container:
                # check for match in child(ren)
                if isinstance(i, list) or isinstance(i, dict):
                    if self._container_has_match(i, r_pattern):
                        return True
                elif isinstance(i, str):
                    if re.search(r_pattern, i):
                        return True
                elif re.search(r_pattern, str(i)):
                    return True

        elif isinstance(container, dict):

            # return True if dict child contains match
            for k,v in container.items():
                if re.search(r_pattern, k):
                    return True
                # check for match in child(ren)
                elif isinstance(v, list) or isinstance(v, dict):
                    if self._container_has_match(v, r_pattern):
                        return True
                elif isinstance(v, str):
                    if re.search(r_pattern, v):
                        return True
                elif re.search(r_pattern, str(v)):
                    return True

        return False

    def _get_matching_container(self, container, r_pattern):
        """
        Returns dict/children items containining match
        """
        matching = []

        if isinstance(container, list):

            # add lists that contain match to matching list
            for i in container:
                # check for matches in child(ren)
                if isinstance(i, list) or isinstance(i, dict):
                    if self._container_has_match(i, r_pattern):
                        matching.append(i)
                elif isinstance(i, str):
                    if re.search(r_pattern, i):
                        matching.append(i)
                else:
                    if re.search(r_pattern, str(i)):
                        matching.append(i)
            return matching

        elif isinstance(container, dict):
            matching = {}

            # add dicts that contain match to matching list
            for k,v in container.items():
                if re.search(r_pattern, k):
                    matches = True
                # check for matches in child(ren)
                elif isinstance(v, list) or isinstance(v, dict):
                    if self._container_has_match(v, r_pattern):
                        matching.update({k:v})
                elif isinstance(v, str):
                    if re.search(r_pattern, v):
                        matching.update({k:v})
                else:
                    if re.search(r_pattern, str(v)):
                        matching.update({k:v})

        return matching

    def _filter_output(self, raw_output, m_pattern):
        """
        Returns filtered output based on given match pattern (m_pattern)
        """

        # convert pattern string into regex pattern
        regex_pattern = fnmatch.translate(m_pattern)
        # filter depending on type
        if isinstance(raw_output, str):
            print_string("Specifying 'filter' is not supported for 'str' return types", title="ERROR")
            return raw_output
        elif isinstance(raw_output, list) or isinstance(raw_output, dict):
            return self._get_matching_container(raw_output, regex_pattern)
        else:
            self.print_string(f"Unhandled return type: {raw_output}", title="ERROR")

    def _get_fields(self, output, fields_str):
        """
        Returns only specific fields from dict or list of dicts
        """
        fields = fields_str.split(',')

        if isinstance(output, dict):
            f_dict = {}

            # add requested fields in order received
            for f in fields:
                f_dict[f] = "N/A"

            for k,v in output.items():
                if k in fields:
                    f_dict[k] = v
#                    f_dict.update({k:v})
            return f_dict
        elif isinstance(output, list):
            f_list = []
            for i in output:
                if isinstance(i, dict):
                    f_dict = {}

                    # add requested fileds in order received
                    for f in fields:
                        f_dict[f] = "N/A"

                    for k,v in i.items():
                        if k in fields:
                            f_dict[k] = v
                    f_list.append(f_dict)
                else:
                    self.print_string(f"Targeting 'field(s)' not supported by this return type: {output}", title="ERROR")
            return f_list
        return

    def _get_context(self, level_list=[]):
        """Returns context specified by level list"""
        f_context = self.full_context

        # iterate through level_list to get to new last context
        for level in level_list:

            # progress through static child
            if f_context['context'].get(level):
                f_context = f_context['context'][level]
            # check if var child
            else:
                # if entry is variable then enter its context
                var_name = ""
                for k,v in f_context.get('context', {}).items():
                    if v.get('is_var', {}):
                        var_name = k

                if var_name:
                    f_context = f_context.get('context')[var_name]

                # print error if not found as static/var child
                else:
                    self.print_string(f"Child '{level}' not found in context: {f_context}", title="ERROR")
        return f_context

### OUTPUT HANDLING ###
    def handle_output(self, raw_output, out_modifiers={}):
        """
        Outputs information from raw_output based on any output modifiers provided in the out_modifiers dict
        """
        fields = out_modifiers.get("fields", "all")
        filter = out_modifiers.get("filter", None)
        if isinstance(raw_output, str):
            format = out_modifiers.get("format", "raw")
        else:
            format = out_modifiers.get("format", "table")

        # handle no output
        if not raw_output:
            self.print_string("No returned values", title="INFO")
            return

        # if dict, sort
        if isinstance(raw_output, dict):
            raw_output = dict(sorted(raw_output.items()))

        # reduce output to items matching filter
        if filter:
            output = self._filter_output(raw_output, filter)
        else:
            output = raw_output

        # reduce output to requested fields, if this is a list or dict
        if fields != "all":
            if isinstance(output, list) or isinstance(output, dict):
                output = self._get_fields(output, fields)
            else:
                self.print_string(f"Specifying fields is only supported by 'dictionary' return types", title="ERROR")

        # finalize output based on format
        if format == "raw":
            print(f"\n{indent(str(output), '  ')}\n")
        elif format == "table":
            if isinstance(output, list):
                # print list of dict table
                print(f'\n{indent(tabulate(output, headers="keys"), "  ")}\n')
            elif isinstance(output, dict):
                # print dict table
                print(f'\n{indent(tabulate(output.items(), headers=["Field", "Value"]), "  ")}\n')
            else:
                print(f'\n{output}\n')
        elif format == "pretty":
            print()
            pprint(output)
            print()
        else:
            self.print_string(f"Unknown format type: {format}", title="ERROR")

    def print_help(self, context, level_list=[], inc_global=True):
        help = self._get_help(context, level_list=level_list)

        print("")
        if help.get('actions'):
            print("  Actions")
            print(f'{indent(tabulate(help["actions"].items()), "  ")}\n')

        if help.get('context'):
            print("  Contexts")
            print(f'{indent(tabulate(help["context"].items()), "  ")}\n')

        if help.get('params'):
            print("  Parameters")
            print(f'{indent(tabulate(help["params"].items()), "  ")}\n')

        if help.get('pipe_params'):
            print("  Pipe Options")
            print(f'{indent(tabulate(help["pipe_params"].items()), "  ")}\n')

        if help.get('options'):
            print("  Options")
            print(f'{indent(tabulate(help["options"].items()), "  ")}\n')

        if inc_global:
            print("  Global Commands")
            print(f'{indent(tabulate(self.global_help.items()), "  ")}\n')

    def print_string(self, msg, title=None):
        """
        Wrapper to print a string to the screen
        """
        if title:
            print(f"\n  {title}: {msg}\n")
        else:
            print(f"\n  {msg}\n")

### INPUT HANDLING ###
    def handle_entry(self, entry):
        """
        Perform context navigation or function based on entry
        """
        entry_list = entry.split()

        # do nothing if entry is empty
        if not entry_list:
            return
        # add entry to script file, if sent in
        elif self.script_file:
            with open(self.script_file, 'a') as f:
                f.write(f"{entry}\n")

        # handle single-word entry
        if len(entry_list) == 1:
            entry = entry.strip()
            if entry in ["logout", "quit"]:
                self.exit_session()

            elif entry in ["top"]:
                self.go_to_top()

            elif entry in ["exit", "back"]:
                # return to top if 1 level deep
                if len(self.level_list) == 1:
                    self.go_to_top()
                    return
                elif not self.level_list:
                    print("  Already at the top")
                    return
                # return one level
                else:
                    self.go_to_context(self.level_list[:-1])

            elif entry in ["history"]:
                self.handle_output(f"\n".join(self._get_history()))

            elif entry.startswith("..") and (entry.endswith("/") or entry.endswith("..")):
                depth = 0 # number of levels to back up to
                for c in entry.split("/"):
                    if c == "..":
                        depth += 1
                if depth > len(self.level_list) - 1:
                    self.go_to_top()
                else:
                    self.go_to_context(self.level_list[:-depth])

            # handle non-global single-word entry
            else:
                self.complete_cmd([entry.strip()], run=True)

        # handle sleep
        elif entry_list[0] == "sleep":
            s_time = entry_list[1]
            if s_time.isdigit():
                self.print_string(f"Sleeping for {s_time} seconds", title="INFO")
                time.sleep(int(s_time))
            else:
                self.print_string("Sleep argument must be an integer (seconds to sleep)", title="ERROR")

        # handle multi-word entry
        else:
            self.complete_cmd(entry_list, run=True)

    def complete_cmd(self, commands, run=False):
        """
        Completes each word of the given command, and runs final command if specified
        """
        is_action = False
        is_ambiguous = False
        leave_space = True
        has_params = False
        is_piped = False
        depth = 0 # number of levels between current context and DD'd parent context
        gathering_string = False
        action_context = None
        do_print_help = False
        out_modifiers = {} # output modifiers
        completed_commands = []

        running_level_list = self.level_list.copy()
        running_params_list = []
        running_string = ""

        ### get running_context ###
        # if starts with top, running_context is top
        if commands[0] == "top":
            completed_commands.append(commands.pop(0))
            running_context = self.full_context
            running_level_list = []
        # if starts with DDs, get running context based on parent depth
        elif ".." in commands[0]:
            # remove typed_text, to be reconstructed through rest of the func
            self.typed_text = ""

            # get depth count
            for c in commands[0].split("/"):
                if c == "..":
                    depth += 1

            # if first command only contains DDs, pop it
            if commands[0].endswith("../") or commands[0].endswith(".."):
                self.handle_output("Does endwith / or ..")
                commands.pop(0)
            # otherwise, replace command with just the context portion
            else:
                first_command = commands.pop(0).split("../")[-1]
                commands.insert(0, first_command)

            # if amount of DDs exceed levels, running_context is top
            if depth > len(self.level_list) - 1:
                running_context = self.full_context
                running_level_list = []
            # otherwise, grab running_context from desired depth
            else:
                running_level_list = self.level_list[:-depth]
                running_context = self._get_context(running_level_list)

        # otherwise, running context is current context
        else:
            running_context = self.context

        ### process each command in commands ###
        for text in commands:
            # if passed pipe, collect output modifiers
            if is_piped:
                # process full kwarg
                if "=" in text:
                    k_name = text.split("=")[0]
                    if k_name in ["fields","filter","format"]:
                        out_modifiers.update({k_name: text.split("=")[1]})
                        completed_commands.append(text)
                        self.typed_text = " ".join(completed_commands)
                    # ignore unknown kwarg
                    else:
                        break
                # process potential partial kwarg
                else:
                    matches = self._get_matches(text, self.pipe_context, level_list=running_level_list)

                    # if unambiguous or exact param match found, autocomplete
                    if len(matches) == 1 or any(text == m["name"] for m in matches):
                        # get completed_param which includes the '='
                        completed_param = f"{matches[0]['name']}="
                        completed_commands.append(completed_param)
                        self.typed_text = " ".join(completed_commands)
                        leave_space = False

                    # if ambiguous param match found, print matches/description
                    elif len(matches) > 1:
                        print(f'\n  Ambiguous matches found for "{text}"')
                        print(f'{indent(tabulate(matches), "  ")}\n')
                        run = False
                        completed_commands.append(text)
                        self.typed_text = " ".join(completed_commands)
                        is_ambiguous = True
                        leave_space = False
                        break
                    # if no matches notify
                    else:
                        self.print_string(f'No modifiers found starting with "{text}"', title="WARNING")
                        break

            # if action was found, collect params
            elif action_context:

                p_var_name = ""
                p_fixed_names = []
                # check if this is a variable param or if there are fixed name params
                for k,v in action_context.get('params', {}).items():
                    if v.get('is_var'):
                        p_var_name = k
                    if v.get('is_fixed'):
                        p_fixed_names.append(k)

                # if gathering string, check for end quotes
                if gathering_string:
                    running_string += f" {text}"

                    # if ending, replace current string with the extended string
                    if text.endswith('"'):
                        text = running_string
                        gathering_string = False
                        running_string = ""
                    # or add to running string and continue
                    else:
                        continue

                # if text is a pipe, begin collecting output modifiers
                if text == "|":
                    # only continue w/ output modifiers if typed command is an action
                    is_piped = True
                    completed_commands.append(text)
                    self.typed_text = " ".join(completed_commands)

                # accept if var arg param
                elif p_var_name:
                    has_params = True
                    running_params_list.append(text)
                    completed_commands.append(text)
                    self.typed_text = " ".join(completed_commands)

                # accept if fixed arg param
                elif text in p_fixed_names:
                    has_params = True
                    running_params_list.append(text)
                    completed_commands.append(text)
                    self.typed_text = " ".join(completed_commands)

                # accept if kwarg param
                elif "=" in text:
                    k_name, eq, value = text.partition("=")
                    # if value starts with quotes, begin collecting string
                    if value.startswith('"') and not value.endswith('"'):
                        running_string += text
                        gathering_string = True
                        continue

                    params = action_context.get("params", {})

                    # if kwarg is defined in params, accept it
                    if k_name in params.keys():
                        has_params = True
                        running_params_list.append(text)
                        completed_commands.append(text)
                        self.typed_text = " ".join(completed_commands)

                    # if kwarg is a defined partial variable, accept it
                    elif any(k_name.startswith(k) and params.get(k, {}).get("is_part_var") for k in params.keys()):
                        has_params = True
                        running_params_list.append(text)
                        completed_commands.append(text)
                        self.typed_text = " ".join(completed_commands)

                    # if kwarg is undefined, notify and break
                    else:
                        self.print_string(f'No params found starting with "{text}":', title="ERROR")
                        break

                # check for autocompletion
                else:
                    # get kwarg key matches in running_context
                    matches = self._get_matches(text, action_context, level_list=running_level_list)

                    # if unambiguous or exact param match found, autocomplete
                    if len(matches) == 1 or any(text == m["name"] for m in matches):
                        # get completed_kwarg
                        match = matches[0]['name']

                        # complete exact match
                        if action_context['params'].get(match):
                            # if fixed param, accept as it
                            if match in p_fixed_names:
                                completed_kwarg = match
                            # else, format as kwarg
                            else:
                                completed_kwarg = f"{match}="

                        # complete unambiguous partial match
                        else:
                            varless_match = match.split("<")[0]
                            completed_kwarg = f"{varless_match}"
                        completed_commands.append(completed_kwarg)
                        self.typed_text = " ".join(completed_commands)
                        leave_space = False

                    # if ambiguous kwarg key match found, print matches/description
                    elif len(matches) > 1:
                        print(f'\n  Ambiguous matches found for "{text}"')
                        print(f'{indent(tabulate(matches), "  ")}\n')
                        run = False
                        completed_commands.append(text)
                        self.typed_text = " ".join(completed_commands)
                        is_ambiguous = True
                        leave_space = False
                        break

                    # if no matches found, notify and break
                    else:
                        self.print_string(f'No params found starting with "{text}"', title="WARNING")
                        break

            # otherwise continue processing command text
            else:
                do_print_help = False

                # get matches in running_context
                matches = self._get_matches(text, running_context, level_list=running_level_list)

                # if unambiguous or exact match found, autocomplete
                if len(matches) == 1 or any(text == m["name"] for m in matches):
                    completed_word = matches[0]['name']
                    completed_commands.append(completed_word)
                    # fixed subcontext
                    if running_context.get('context', {}).get(completed_word):
                        running_context = running_context['context'][completed_word]
                    # action
                    elif running_context.get('actions', {}).get(completed_word):
                        running_context = running_context['actions'][completed_word]
                        is_action = True
                        action_context = running_context.copy()
                    # var subcontext
                    else:
                        # find variable child and change to it's context
                        c_var_name = ""
                        for k,v in running_context.get('context', {}).items():
                            if v.get('is_var', {}):
                                c_var_name = k
                        running_context = running_context['context'][k]
                    running_level_list.append(completed_word)
                    self.typed_text = " ".join(completed_commands)

                # if ambiguous match found, print matches and descriptions
                elif len(matches) > 1:
                    print(f'\n  Ambiguous matches found for "{text}"')
                    print(f'{indent(tabulate(matches), "  ")}\n')

                    run = False
                    completed_commands.append(text)
                    self.typed_text = " ".join(completed_commands)
                    is_ambiguous = True
                    leave_space = False
                    break

                else:
                    # check if this is a variable context
                    c_var_name = ""
                    for k,v in running_context.get('context', {}).items():
                        if v.get('is_var', {}):
                            c_var_name = k

                    # accept variable context and print help
                    if c_var_name:
                        running_context = running_context['context'][k]
                        running_level_list.append(text)
                        completed_commands.append(text)
                        self.typed_text = " ".join(completed_commands)
                        do_print_help = True

                    else:
                        # if no matches found, break
                        if not action_context:
                            self.print_string(f'No commands found starting with "{text}"', title="INFO")
                        run = False
                        completed_commands.append(text)
                        self.typed_text = " ".join(completed_commands)
                        break

        # if run was specified execute action or switch contexts
        if run:
            # validate, if configured for this endpoint
            validation_func = running_context.get("validation_func")
            if validation_func:
                validation = self.handler_func(self.handler, validation_func, level_list=running_level_list, params=running_params_list)
            # otherwise make any input valid
            else:
                validation = True

            # return if validation failed
            if not validation == True:
                self.print_string(validation, title="ERROR")
                return

            # execute if final word is an action
            if is_action:
                # use defined run_func or name of action if not defined
                run_func = running_context.get('run_func', running_level_list[-1])
                req_params = self._get_required_params(action_context)

                # if has a run_func assigned, have handler run it
                if run_func:
                    if req_params:
                        missing_req_params = []
                        typed_params = [p.split("=")[0] for p in running_params_list]

                        # get missing required params
                        for p in req_params:
                            if p not in typed_params:
                                # add to missing_req_params if not a variable param
                                if "_VAR" not in p:
                                    missing_req_params.append(p)

                        # notify of missing params and retain typed_text
                        if missing_req_params:
                            results = f"ERROR: Missing required parameter(s): {' | '.join(missing_req_params)}"
                            self.typed_text = " ".join(completed_commands)
                            self.retain_text = True
                        else:
                            results = self.handler_func(self.handler, run_func, level_list=running_level_list, params=running_params_list)
                    elif has_params:
                        results = self.handler_func(self.handler, run_func, level_list=running_level_list, params=running_params_list)
                    else:
                        results = self.handler_func(self.handler, run_func, level_list=running_level_list)

                    # output results
                    if not out_modifiers:
                        self.handle_output(results)
                    else:
                        self.handle_output(results, out_modifiers)

            # if not action, switch context
            else:
                self.update_context(running_context, running_level_list)

        # otherwise retain completed text
        else:
            self.retain_text = True

            # if this is from a parent context, prepend appropriate number of DDs to typed_text
            if depth > 0:
                self.typed_text = f"{'../' * depth}{self.typed_text}"
                # leave no space if tabbing on initial DDs
                if self.typed_text.endswith("../"):
                    leave_space = False

            # if command is unchanged or do_print_help, print help for running context
            if commands == completed_commands or do_print_help:
                # if no ambiguous matches found
                if not is_ambiguous:
                    # print pipe help if piped
                    if is_piped:
                        self.print_help(self.pipe_context, level_list=running_level_list, inc_global=False)

                    # otherwise print context help
                    else:
                        self.print_help(running_context, level_list=running_level_list, inc_global=False)
            # if command starts at top print help from running context
            elif completed_commands[0] == "top":
                self.print_help(running_context, level_list=running_level_list, inc_global=False)

            # add space after typed_text if unambiguous
            if leave_space:
                self.typed_text += " "

    def tabbed(self):
        commands = self.typed_text.split()

        # if entry is empty, print help
        if not commands:
            self.print_help(self.context, level_list=self.level_list, inc_global=False)

        # if single word was typed, evaluate for completion or context help
        elif len(commands) == 1:
            self.complete_cmd(commands)

        # if multiple words were typed,
        else:
            self.complete_cmd(commands)

    def handle_events(self):
        """
        Handle events (key-presses) if needed
        """
        if self.handle_clear_screen:
            self.clear_screen()
            self.handle_clear_screen = False
        elif self.handle_help:
            if not self.typed_text:
                self.print_help(self.context)
            else:
                self.complete_cmd(self.typed_text.split())
            self.handle_help = False
        elif self.handle_tab:
            self.tabbed()
            self.handle_tab = False

### HANDLER ###
    def handler_func(self, handler, func_name, level_list=[], params=[]):
        """
        Runs func_name function on handler with args
        """

        try:
            h_func = getattr(handler, func_name)
            if callable(h_func):
                return h_func(level_list=level_list, params=params)
            else:
                return f"Function not callable: {func_name}"
        except AttributeError:
            return f"Function not found on handler: '{func_name}'"

### NAVIGATION ###
    def go_to_context(self, level_list=[]):
        """Go to context specified by level list"""
        parent_context = self._get_context(level_list=level_list)

        self.update_context(parent_context, level_list)

    def go_to_top(self):
        """
        Go to main (top) context
        """
        self.update_context(self.full_context, [])

    def update_context(self, new_context, new_level_list):
        self.context = new_context
        self.level_list = new_level_list

        # update prompt
        if self.context == self.full_context:
            self.prompt = "top# "
        else:
            self.prompt = f"{self.context.get('prompt', '/'.join(self.level_list))}# "
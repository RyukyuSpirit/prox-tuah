import os
import sys
import colorama
import re
import fnmatch
from prompt_toolkit import prompt,PromptSession
from prompt_toolkit.application.current import get_app
from prompt_toolkit.application import run_in_terminal
from prompt_toolkit.key_binding import KeyBindings
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
        self.global_help = {
            "exit": "Go back one context",
            "main": "Return to main context",
            "quit": "Quit application",
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
        self.session = PromptSession() # The prompt session
        self.handle_help = False # should help be displayed before next prompt
        self.handle_tab = False # should tab press be handled before next prompt
        self.handle_clear_screen = False # should screen be cleared before next prompt
        self.retain_text = False # should typed_text be inserted into next prompt

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

    def print_help(self, context, inc_global=True):
        help = self.get_help(context)

        print("")
        if help.get('actions'):
            print("  Actions")
            print(f'{indent(tabulate(help['actions'].items()), "  ")}\n')

        if help.get('context'):
            print("  Contexts")
            print(f'{indent(tabulate(help['context'].items()), "  ")}\n')

        if help.get('params'):
            print("  Parameters")
            print(f'{indent(tabulate(help['params'].items()), "  ")}\n')

        if help.get('pipe_params'):
            print("  Pipe Options")
            print(f'{indent(tabulate(help['pipe_params'].items()), "  ")}\n')

        if inc_global:
            print("  Global Commands")
            print(f'{indent(tabulate(self.global_help.items()), "  ")}\n')

    def _get_matches(self, text, context):
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

        return matches

    def get_required_params(self, action_context):
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


    def complete_cmd(self, commands, run=False):
        """
        Completes each word of the given command, and runs final command if specified
        """
        is_action = False
        is_ambiguous = False
        leave_space = True
        is_same = False
        has_params = False
        is_piped = False
        gathering_string = False
        action_context = None
        do_print_help = False
        out_modifiers = {} # output modifiers
        completed_commands = []

        running_context = self.context
        running_level_list = self.level_list.copy()
        running_params_list = []
        running_string = ""

        # process each text in command line
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
                    matches = self._get_matches(text, self.pipe_context)

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
                        self.print_error(f'No modifiers found starting with "{text}"', severity="wARNING")
                        break

            # if action was found, collect params
            elif action_context:

                # check if this is a variable param
                p_var_name = ""
                for k,v in action_context.get('params', {}).items():
                    if v.get('is_var', {}):
                        p_var_name = k

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

                # accept if kwarg param
                elif "=" in text:
                    k_name, eq, value = text.partition("=")
                    # if value starts with quotes, begin collecting string
                    if value.startswith('"') and not value.endswith('"'):
                        running_string += text
                        gathering_string = True
                        continue

                    # if kwarg is defined in params, accept it
                    if action_context.get("params", {}).get(k_name):
                        has_params = True
                        running_params_list.append(text)
                        completed_commands.append(text)
                        self.typed_text = " ".join(completed_commands)
                    # if kwarg is undefined, notify and break
                    else:
                        self.print_error(f'No params found starting with "{text}":')
                        break

                # check for autocompletion
                else:
                    # get kwarg key matches in running_context
                    matches = self._get_matches(text, action_context)

                    # if unambiguous or exact param match found, autocomplete
                    if len(matches) == 1 or any(text == m["name"] for m in matches):
                        # get completed_kwarg which includes the '='
                        completed_kwarg = f"{matches[0]['name']}="
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
                        self.print_error(f'No params found starting with "{text}"', severity="WARNING")
                        break

            # otherwise continue processing command text
            else:
                do_print_help = False

                # get matches in running_context
                matches = self._get_matches(text, running_context)

                # if unambiguous or exact param match found, autocomplete
                if len(matches) == 1 or any(text == m["name"] for m in matches):
                    completed_word = matches[0]['name']
                    completed_commands.append(completed_word)
                    if running_context.get('context', {}).get(completed_word):
                        running_context = running_context['context'][completed_word]
                    elif running_context.get('actions', {}).get(completed_word):
                        running_context = running_context['actions'][completed_word]
                        is_action = True
                        action_context = running_context.copy()
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
                            self.print_error(f'No commands found starting with "{text}"', severity="INFO")
                        run = False
                        completed_commands.append(text)
                        self.typed_text = " ".join(completed_commands)
                        break

        # if run was specified execute action or switch contexts
        if run:
            # execute if final word is an action
            if is_action:
                # use defined run_func or name of action if not defined
                run_func = running_context.get('run_func', running_level_list[-1])
                req_params = self.get_required_params(action_context)

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
                            results = f"Missing required parameter(s): {' | '.join(missing_req_params)}"
                            completed_commands.append(text)
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

            # if command is unchanged or do_print_help, print help for running context
            if commands == completed_commands or do_print_help:
                # if no ambiguous matches found
                if not is_ambiguous:
                    # print pipe help if piped
                    if is_piped:
                        self.print_help(self.pipe_context, inc_global=False)

                    # otherwise print context help
                    else:
                        self.print_help(running_context, inc_global=False)

            # add space after typed_text if unambiguous
            if leave_space:
                self.typed_text += " "

    def tabbed(self):
        commands = self.typed_text.split()

        # if entry is empty, print help
        if not commands:
            self.print_help(self.context, inc_global=False)


        # if single word was typed, evaluate for completion or context help
        elif len(commands) == 1:
            self.complete_cmd(commands)

        # if multiple words were typed,
        else:
            self.complete_cmd(commands)

    def get_help(self, context):
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
                elif k == "actions":
                    for ck,cv in v.items():
                        if cv.get("description"):
                            help["actions"].update({ck: cv.get("description")})
                elif k == "params":
                    for ck,cv in v.items():
                        if cv.get("description"):
                            if cv.get("is_var"):
                                help["params"].update({f'<{ck}>': cv.get("description")})
                            elif cv.get("is_part_var"):
                                var_suffix = cv.get("var_suffix", "N")
                                help["params"].update({f'{ck}<{var_suffix}>': cv.get("description")})
                            else:
                                help["params"].update({f'{ck}=': cv.get("description")})
                elif k == "pipe_params":
                    for ck,cv in v.items():
                        if cv.get("description"):
                            help["pipe_params"].update({f'{ck}=': cv.get("description")})

        return help

    def update_context(self, new_context, new_level_list):
        self.context = new_context
        self.level_list = new_level_list

        # update prompt
        if self.context == self.full_context:
            self.prompt = "main# "
        else:
            self.prompt = f"{self.context.get('prompt', '/'.join(self.level_list))}# "

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

    def start(self):

        self.clear_screen()
        self.go_to_main()
        self.run()

    def run(self):
        print(f"{self.welcome}")
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
                break

            self.handle_entry(self.entry)

    def go_to_main(self):
        """
        Go to main (top) context
        """
        self.update_context(self.full_context, [])

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

    def print_error(self, msg, severity="ERROR"):
        """
        Wrapper to print an error message to the screen
        """
        print(f"\n  {severity}: {msg}\n")

    def container_has_match(self, container, r_pattern):
        """
        Returns True if container's child contains a match
        """
        if isinstance(container, list):
            # return True if list child contains match
            for i in container:
                # check for match in child(ren)
                if isinstance(i, list) or isinstance(i, dict):
                    if self.container_has_match(i, r_pattern):
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
                    if self.container_has_match(v, r_pattern):
                        return True
                elif isinstance(v, str):
                    if re.search(r_pattern, v):
                        return True
                elif re.search(r_pattern, str(v)):
                    return True

        return False

    def get_matching_container(self, container, r_pattern):
        """
        Returns dict/children items containining match
        """
        matching = []

        if isinstance(container, list):

            # add lists that contain match to matching list
            for i in container:
                # check for matches in child(ren)
                if isinstance(i, list) or isinstance(i, dict):
                    if self.container_has_match(i, r_pattern):
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
                    if self.container_has_match(v, r_pattern):
                        matching.update({k:v})
                elif isinstance(v, str):
                    if re.search(r_pattern, v):
                        matching.update({k:v})
                else:
                    if re.search(r_pattern, str(v)):
                        matching.update({k:v})

        return matching


    def filter_output(self, raw_output, m_pattern):
        """
        Returns filtered output based on given match pattern (m_pattern)
        """

        # convert pattern string into regex pattern
        regex_pattern = fnmatch.translate(m_pattern)
        # filter depending on type
        if isinstance(raw_output, str):
            print_error("Specifying 'filter' is not supported for 'str' return types")
            return raw_output
        elif isinstance(raw_output, list) or isinstance(raw_output, dict):
            return self.get_matching_container(raw_output, regex_pattern)
        else:
            self.print_error(f"Unhandled return type: {raw_output}")

    def get_fields(self, output, fields_str):
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
                    self.print_error(f"Targeting 'field(s)' not supported by this return type: {output}")
            return f_list
        return


    def handle_output(self, raw_output, out_modifiers={}):
        """
        Outputs information from raw_output based on any output modifiers provided in the out_modifiers dict
        """
        fields = out_modifiers.get("fields", "all")
        filter = out_modifiers.get("filter", None)
        format = out_modifiers.get("format", "table")

        # reduce output to items matching filter
        if filter:
            output = self.filter_output(raw_output, filter)
        else:
            output = raw_output

        # reduce output to requested fields, if this is a list or dict
        if fields != "all":
            if isinstance(output, list) or isinstance(output, dict):
                output = self.get_fields(output, fields)
            else:
                print_error(f"Specifying fields is only supported by 'dictionary' return types")

        # finalize output based on format
        if format == "raw":
            print(f"\n  {output}\n")
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
            self.print_error(f"Unknown format type: {format}")

    def handle_entry(self, entry):
        """
        Perform context navigation or function based on entry
        """
        entry_list = entry.split()

        # do nothing if entry is empty
        if not entry_list:
            return

        # handle single-word entry
        elif len(entry_list) == 1:
            entry = entry.strip()
            if entry in ["logout", "quit"]:
                print("  Terminating session...")
                sys.exit()

            elif entry in ["main", "top"]:
                self.go_to_main()

            elif entry in ["exit", "back"]:
                # return to main menu if 1 level deep
                if len(self.level_list) == 1:
                    self.go_to_main()
                    return
                elif not self.level_list:
                    print("  Already at the main menu")
                    return
                # return one level
                else:
                    self.level_list.pop()
                    back_context = self.full_context
                    last_level = self.level_list[-1]
                    # iterate through level_list to get to new last context
                    for level in self.level_list:

                        # progress through static child
                        if back_context['context'].get(level):
                            back_context = back_context['context'][level]
                        # check if var child
                        else:
                            # if entry is variable then enter its context
                            var_name = ""
                            for k,v in back_context.get('context', {}).items():
                                if v.get('is_var', {}):
                                    var_name = k

                            if var_name:
                                back_context = back_context.get('context')[var_name]

                            # print error if not found as static/var child
                            else:
                                self.print_error(f"Child '{level}' not found in context: {back_context}")

                    self.update_context(back_context, self.level_list)

            # handle non-global single-word entry
            else:
                self.complete_cmd([entry.strip()], run=True)

        # handle multi-word entry
        else:
            self.complete_cmd(self.entry.split(), run=True)

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

    def quit(self, argline):
        """
        Close application
        """
        sys.exit(0)


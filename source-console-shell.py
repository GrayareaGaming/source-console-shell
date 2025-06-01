#!/usr/bin/env python3
import socket
import sys
import os
import threading
import queue
import select
import time
import re
import argparse
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.shortcuts import CompleteStyle
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.completion import Completer, Completion, WordCompleter, ThreadedCompleter
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import HTML

class SourceConsoleHistory:
    def __init__(self, histfile=None):
        self.histfile = histfile or os.path.join(os.path.expanduser("~"), ".sourceconsole_history")
        self.file_history = FileHistory(self.histfile)

class SourceConsole:
    def __init__(self, port=8020, continuous_output=True, verbose=True, interactive=True):
        self.port = port
        self.sock = None
        self.running = False
        self.output_queue = queue.Queue()
        self.lock = threading.Lock()
        self.last_command = None
        self.is_autocomplete_query = False
        self.autocomplete_results = {}
        self.autocomplete_lock = threading.Lock()
        self.query_in_progress = {}
        self.cvar_list = []
        self.suppress_output = False
        self.suppress_lock = threading.Lock()
        self.continuous_output = continuous_output
        self.verbose = verbose
        self.interactive = interactive

    def connect(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(3)
            self.sock.connect(('localhost', self.port))
            self.sock.setblocking(False)
            if self.verbose:
                print(f"Connected to Source Engine console on port {self.port}.")
            self.running = True
            self.read_thread = threading.Thread(target=self.read_output, daemon=True)
            self.read_thread.start()
            # Start continuous output thread if enabled
            if self.continuous_output:
                self.output_display_thread = threading.Thread(target=self.display_continuous_output, daemon=True)
                self.output_display_thread.start()
            if self.interactive:
                # Load CVAR list on startup
                self.load_cvar_list()
            return True
        except ConnectionRefusedError:
            print(f"Error: Connection refused on port {self.port}. Is the game running with -netconport {self.port}?", file=sys.stderr)
            return False
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return False

    def read_output(self):
        while self.running:
            try:
                readable, _, _ = select.select([self.sock], [], [], 0.1)
                if self.sock in readable:
                    data = self.sock.recv(4096)
                    if not data:
                        self.running = False
                        self.output_queue.put(("Connection closed by server.", False))
                        break
                    output = data.decode('utf-8', errors='ignore')
                    if output:
                        # replace \r\n with \n for consistent line endings
                        output = output.replace('\r\n', '\n')
                        self.output_queue.put((output, self.is_autocomplete_query))
            except socket.error:
                continue
            except Exception as e:
                self.output_queue.put((f"Read error: {e}", False))
                print(f"Read error: {e}", file=sys.stderr)
                break

    def send_command(self, cmd, is_autocomplete=False, wait_for_output=True):
        if not self.running:
            print("Error: Not connected to Source Engine console.", file=sys.stderr)
            return False
        try:
            with self.lock:
                self.last_command = cmd
                self.is_autocomplete_query = is_autocomplete
                self.sock.send((cmd + '\n').encode())
            if wait_for_output:
                deadline = time.time() + 0.5
                while time.time() < deadline:
                    if not self.output_queue.empty():
                        break
                    time.sleep(0.01)
            return True
        except Exception as e:
            if self.verbose:
                print(f"Error sending command: {e}", file=sys.stderr)
            self.running = False
            return False

    def get_output(self, timeout=0.5, filter_autocomplete=True):
        result = ''
        stop_time = time.time() + timeout
        while time.time() < stop_time:
            try:
                output, is_autocomplete = self.output_queue.get_nowait()
                if filter_autocomplete or not is_autocomplete:
                    result += output
                stop_time = time.time() + timeout  # Reset timeout on new output
            except queue.Empty:
                time.sleep(0.01)
                continue
        return result
    
    def get_output_lines(self, timeout=0.5, filter_autocomplete=True):
        return self.get_output(timeout, filter_autocomplete).splitlines()

    def display_continuous_output(self):
        """Continuously fetch and display console output in a separate thread."""
        while self.running:
            try:
                with self.suppress_lock:
                    if self.suppress_output:
                        time.sleep(0.01)
                        continue
                    output, _ = self.output_queue.get(timeout=0.05)
                    print(output, end='', flush=True)
            except queue.Empty:
                time.sleep(0.01)
                continue
            except Exception as e:
                print(f"Error in continuous output: {e}", file=sys.stderr)

    def load_cvar_list(self):
        """Load CVAR list by running the 'cvarlist' command."""
        try:
            with self.suppress_lock:
                self.suppress_output = True  # Suppress output during cvarlist

            while not self.output_queue.empty():
                self.output_queue.get_nowait()

            self.send_command("cvarlist", is_autocomplete=True, wait_for_output=False)

            output_lines = self.get_output_lines(filter_autocomplete=True)

            cvar_list = []
            for line in output_lines:
                parts = line.split(":")
                if parts and parts[0].strip():
                    cvar_list.append(parts[0].strip())

            self.cvar_list = sorted(cvar_list)
            if self.verbose:
                print(f"Loaded {len(self.cvar_list)} CVARs for autocompletion.")
        except Exception as e:
            print(f"Error loading CVAR list: {e}", file=sys.stderr)
            self.cvar_list = []
        finally:
            with self.suppress_lock:
                self.suppress_output = False

    def query_entities(self, prefix, find_class_names=False, find_entity_names=True):
        """Query class names and/or entity names and store results in autocomplete_results."""
        try:
            with self.suppress_lock:
                self.suppress_output = True  # Suppress output during query_entities

            while not self.output_queue.empty():
                self.output_queue.get_nowait()

            self.send_command(f"find_ent {prefix}", is_autocomplete=True, wait_for_output=False)

            output_lines = self.get_output_lines(timeout=0.1, filter_autocomplete=True)

            class_names = []
            entity_names = []
            for line in output_lines:
                match = re.match(r"\s*'(?P<class>.*?)'\s*:\s*'(?P<entity>.*?)'", line)
                if match:
                    class_name = match.group('class')
                    entity_name = match.group('entity')
                    if find_class_names and class_name.lower().startswith(prefix.lower()):
                        class_names.append(class_name)
                    if find_entity_names and entity_name.lower().startswith(prefix.lower()):
                        entity_names.append(entity_name)

            # Combine and deduplicate results
            combined_results = sorted(set(class_names + entity_names))

            with self.autocomplete_lock:
                self.autocomplete_results[prefix] = combined_results
                self.query_in_progress[prefix] = False
        except Exception as e:
            if self.verbose:
                print(f"Error querying entities: {e}", file=sys.stderr)
            with self.autocomplete_lock:
                self.autocomplete_results[prefix] = []
                self.query_in_progress[prefix] = False
        finally:
            with self.suppress_lock:
                self.suppress_output = False

    def close(self):
        self.running = False
        if self.sock:
            self.sock.close()
        self.sock = None

# Custom completer that handles CVARs and entity/class names
class SourceConsoleCompleter(Completer):
    def __init__(self, console):
        self.console = console
        self.cvar_completer = WordCompleter(self.console.cvar_list, ignore_case=True)
        # Commands that take entity names as their first argument
        self.entity_commands = {"ent_fire", "ent_dump", "ent_keyvalue"}
        # Commands that take either class names or entity names as their first argument
        self.class_entity_commands = {"ent_text", "ent_messages"}
        self.last_prefix = None

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        words = text.split()

        # Handle commands that take either class names or entity names
        if len(words) >= 1 and words[0].lower() in self.class_entity_commands:
            if len(words) == 1:
                for cmd in self.class_entity_commands:
                    if cmd.startswith(text.lower()):
                        yield Completion(cmd, start_position=-len(text), display=cmd)
            else:
                arg = words[-1]
                with self.console.autocomplete_lock:
                    if arg != self.last_prefix or arg not in self.console.autocomplete_results:
                        self.last_prefix = arg
                        self.console.query_in_progress[arg] = True
                        threading.Thread(
                            target=self.console.query_entities,
                            args=(arg, True, True),  # Find both class names and entity names
                            daemon=True
                        ).start()
                    else:
                        results = self.console.autocomplete_results.get(arg, [])
                        for result in results:
                            yield Completion(
                                result,
                                start_position=-len(words[-1]),
                                display=result
                            )
                        return

                start_time = time.time()
                while time.time() - start_time < 1.0:
                    with self.console.autocomplete_lock:
                        if not self.console.query_in_progress.get(arg, False):
                            results = self.console.autocomplete_results.get(arg, [])
                            for result in results:
                                yield Completion(
                                    result,
                                    start_position=-len(words[-1]),
                                    display=result
                                )
                            break
                    time.sleep(0.05)

        # Handle commands that take only entity names
        elif len(words) >= 1 and words[0].lower() in self.entity_commands:
            if len(words) == 1:
                for cmd in self.entity_commands:
                    if cmd.startswith(text.lower()):
                        yield Completion(cmd, start_position=-len(text), display=cmd)
            else:
                arg = words[-1]
                with self.console.autocomplete_lock:
                    if arg != self.last_prefix or arg not in self.console.autocomplete_results:
                        self.last_prefix = arg
                        self.console.query_in_progress[arg] = True
                        threading.Thread(
                            target=self.console.query_entities,
                            args=(arg, False, True),  # Find only entity names
                            daemon=True
                        ).start()
                    else:
                        entity_names = self.console.autocomplete_results.get(arg, [])
                        for entity_name in entity_names:
                            yield Completion(
                                entity_name,
                                start_position=-len(words[-1]),
                                display=entity_name
                            )
                        return

                start_time = time.time()
                while time.time() - start_time < 1.0:
                    with self.console.autocomplete_lock:
                        if not self.console.query_in_progress.get(arg, False):
                            entity_names = self.console.autocomplete_results.get(arg, [])
                            for entity_name in entity_names:
                                yield Completion(
                                    entity_name,
                                    start_position=-len(words[-1]),
                                    display=entity_name
                                )
                            break
                    time.sleep(0.05)

        # Handle 'help' command with CVAR autocompletion
        elif len(words) >= 1 and words[0].lower() == "help":
            if len(words) == 1:
                if "help".startswith(text.lower()):
                    yield Completion("help", start_position=-len(text), display="help")
            else:
                arg = words[-1].lower()
                for cmd in self.console.cvar_list:
                    if cmd.lower().startswith(arg):
                        yield Completion(cmd, start_position=-len(words[-1]), display=cmd)
        # General CVAR autocompletion
        else:
            for completion in self.cvar_completer.get_completions(document, complete_event):
                yield completion

def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Source Engine Console Shell")
    parser.add_argument(
        "--port",
        type=int,
        default=8020,
        help="Port to connect to the Source Engine console (default: 8020)"
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default="$",
        help="Prompt text to display (default: '$')"
    )
    parser.add_argument(
        "--no-continuous-output",
        action="store_true",
        help="Disable continuous fetching of console output (default: enabled)"
    )
    parser.add_argument(
        "-e",
        "--eval",
        type=str,
        help="Run a single command and exit (non-interactive mode)"
    )
    parser.add_argument(
        "-s",
        "--script",
        type=str,
        help="Run a script command (equivalent to --eval 'script <value>') and exit (non-interactive mode)"
    )
    parser.add_argument(
        "--dump-scope",
        type=str,
        help="Run script __DumpScope(0, <value>) and exit (non-interactive mode)"
    )
    parser.add_argument(
        "--dump-root-scope",
        "--dump-root-table",
        action="store_true",
        help="Run script __DumpScope(0, getroottable()) and exit (non-interactive mode)"
    )
    args = parser.parse_args()

    # Determine the command to run in non-interactive mode
    if args.eval:
        args.command = args.eval
    elif args.script:
        args.command = f"script {args.script}"
    elif args.dump_scope:
        args.command = f"script __DumpScope(0, {args.dump_scope})"
    elif args.dump_root_scope:
        args.command = "script __DumpScope(0, getroottable())"
    else:
        args.command = None

    return args

def main():
    args = parse_args()
    port = args.port
    prompt_text = args.prompt
    continuous_output = not args.no_continuous_output
    interactive = args.command is None
    non_interactive = not interactive
    verbose = interactive

    try:
        main_console = SourceConsole(
            port=port,
            continuous_output=continuous_output and interactive,
            verbose=verbose,
            interactive=interactive
        )
        if not main_console.connect():
            return

        if non_interactive:
            # Non-interactive mode: run the command and exit
            main_console.send_command(args.command, is_autocomplete=False)
            output = main_console.get_output(filter_autocomplete=False)
            print(output, end='')
            return

        # Interactive mode
        if verbose:
            print("Source Engine Console Shell")
            print("Type 'exit' to leave, Ctrl+C to clear prompt, Ctrl+R for reverse search")
            print(f"Type 'help <cmd>' and press Tab to autocomplete CVARs (e.g., 'help ent_')")
            print(f"Type 'ent_dump <name>' or 'ent_text <class/entity>' and press Tab to autocomplete names (e.g., 'ent_text prop')")
            print("-" * 60)

        base_completer = SourceConsoleCompleter(main_console)
        completer = ThreadedCompleter(base_completer)

        bindings = KeyBindings()

        @bindings.add('c-c')
        def _(event):
            event.app.current_buffer.reset()

        style = Style.from_dict({
            'prompt': '#00f bold',
            '': '#0f0',
        })

        session = PromptSession(
            HTML(f'<prompt>{prompt_text}> </prompt>'),
            style=style,
            history=history_manager.file_history,
            completer=completer,
            complete_style=CompleteStyle.READLINE_LIKE,
            key_bindings=bindings,
        )

        while True:
            try:
                cmd = session.prompt().strip()

                if cmd.lower() == 'exit':
                    break
                elif cmd == '':
                    continue

                main_console.send_command(cmd, is_autocomplete=False)

                if not main_console.continuous_output:
                    output = main_console.get_output(filter_autocomplete=False)
                    print(output, end='', flush=True)

            except (KeyboardInterrupt, EOFError):
                print("\nExiting...")
                break

    except EOFError:
        print("\nExiting...", file=sys.stderr)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
    finally:
        main_console.close()
        if verbose:
            print("Goodbye!")


if __name__ == "__main__":
    history_manager = SourceConsoleHistory()
    main()

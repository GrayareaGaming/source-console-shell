# Source Engine Console Shell

A command-line tool for interacting with Source Engine game consoles (e.g., Portal 2, Left 4 Dead 2, etc) over TCP, with autocompletion and command history.

## Features
- Connects to a Source Engine game console via TCP (default port 8020).
- Provides an interactive shell with command history and autocompletion.
- Autocompletes CVARs using the `cvarlist` command (loaded at startup).
- Autocompletes entity names for commands like `ent_fire`, `ent_dump`, and `ent_keyvalue` using the `find_ent` command.
- Autocompletes both class names and entity names for commands like `ent_text` and `ent_messages` which do not have auto-complete in-game.
- Continuously displays console output (e.g., game logs) in interactive mode, with an option to disable this behavior.
- Non-interactive mode to run a single command and exit.
- Options to dump scope information using `__DumpScope` in non-interactive mode.
- Customizable port and prompt text via command-line arguments.
- Colorized text in interactive mode.
- Ctrl+C clears the prompt; Ctrl+R enables reverse search through command history in interactive mode.

## Prerequisites
- A Source Engine game (e.g., Portal 2) running with the `-netconport` launch option (e.g., `-netconport 8020`).
- Python 3.6 or later.
- The `prompt_toolkit` library (version 3.0.51 recommended).

## Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/source-console-shell.git
   cd source-console-shell
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Configuring the Game via Steam
To use this tool, your Source Engine game must be configured to enable the network console port. Follow these steps in Steam to set the `-netconport` launch option:

1. **Open Steam and Navigate to Your Game**:
   - Open the Steam client and go to your Library.
   - Find the Source Engine game you want to use (e.g., Portal 2, Half-Life 2, Team Fortress 2).

2. **Access Properties**:
   - Right-click on the game in your Library.
   - Select "Properties" from the context menu.
   - Enter the following in the "Launch Options" field:
     ```
     -netconport 8020
     ```
     Replace `8020` with a different port if desired (ensure the port matches the one used when running the script).

3. **Close Properties and Launch the Game**:
   - Close the Properties window.
   - Launch the game from Steam. It will now listen for network console connections on the specified port.

## Usage
### Interactive Mode
1. Ensure your Source Engine game is running with the `-netconport` option as configured above.

2. Run the console shell in interactive mode:
   ```bash
   python source-console-shell.py --port 8020 --prompt p2
   ```

   - `--port`: Specify the port to connect to (default: 8020; must match the game's `-netconport` setting).
   - `--prompt`: Specify the prompt text (default: "$").
   - `--no-continuous-output`: Disable continuous fetching of console output (default: enabled).

3. Interact with the console:
   - Type commands like `echo hello` or `ent_fire myent` and press Enter.
   - Press Tab to autocomplete CVARs (e.g., `ent_`) or entity/class names (e.g., `myent` after `ent_fire`, `prop` after `ent_text`).
   - Use Ctrl+C to clear the prompt, Ctrl+R for reverse search, and type `exit` to quit.
   - With continuous output enabled (default), game console output (e.g., server logs) will appear.

### Non-Interactive Mode
You can run a single command and exit without entering the interactive prompt, similar to `node -e`. Only the command's output will be displayed, making it suitable for redirecting to a file.

1. **Run a Custom Command**:
   ```bash
   python source-console-shell.py --port 8020 -e "echo hello"
   ```
   - `-e`/`--eval`: Specify a command to run and exit (e.g., `echo hello`).

2. **Dump Scope with a Specific Value**:
   ```bash
   python source-console-shell.py --port 8020 --dump-scope "some_scope"
   ```
   - `--dump-scope`: Run `script __DumpScope(0, <value>)` with the specified value (e.g., `some_scope`) and exit.

3. **Dump Root Scope**:
   ```bash
   python source-console-shell.py --port 8020 --dump-root-scope > root-scope.txt
   ```
   - `--dump-root-scope`: Run `script __DumpScope(0, getroottable())` and exit.
   - **Note**: This command typically produces thousands of lines of output, so it’s recommended to redirect the output to a file using `>` (e.g., `> root-scope.txt`).

**Note**: If multiple non-interactive options are specified, the priority is: `--eval`, `--dump-scope`, `--dump-root-scope`.

## Example
### Interactive Mode
```bash
$ python source-console-shell.py --port 8020 --prompt p2
Source Engine Console Shell
Type 'exit' to leave, Ctrl+C to clear prompt, Ctrl+R for reverse search
Type 'help <cmd>' and press Tab to autocomplete CVARs (e.g., 'help ent_')
Type 'ent_dump <name>' or 'ent_text <class/entity>' and press Tab to autocomplete names (e.g., 'ent_text prop')
------------------------------------------------------------
Connected to Source Engine console on port 8020.
Loaded 3462 CVARs for autocompletion.
p2> ent_text prop [Tab]
```

### Non-Interactive Mode
```bash
$ python source-console-shell.py --port 8020 -e "echo hello"
hello
```

```bash
$ python source-console-shell.py --port 8020 --dump-root-scope > root-scope.txt
# Output redirected to root-scope.txt
```

## Contributing
Contributions are welcome! Please submit a pull request or open an issue on GitHub to suggest improvements or report bugs.

## License
This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Acknowledgments
- Shout out to [PortalRunner](https://www.youtube.com/watch?v=-v5vCLLsqbA) for his video on the `-netconport` feature.
- Built with [prompt_toolkit](https://python-prompt-toolkit.readthedocs.io/en/master/) for the interactive shell and autocompletion.

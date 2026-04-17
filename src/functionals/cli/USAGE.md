# Building CLI Tools With `functionals.cli`

`functionals.cli` is now module-first: you define commands with module-level
decorators (`register`, `argument`, `option`) and execute them with `run()`.

## Quick Start

```python
import functionals.cli as cli


@cli.register(description="Greet someone")
@cli.argument("name", type=str, help="Person to greet")
@cli.option("--greet")
@cli.option("-g")
def greet(name: str) -> str:
    return f"Hello, {name}!"


if __name__ == "__main__":
    cli.run()
```

## Example 2

```python
from __future__ import annotations

from enum import StrEnum
from time import strftime

import functionals.cli as cli
import functionals.db as db
from functionals.db import db_field
from pydantic import BaseModel

DB_PATH = "todos.db"
TABLE = "todos"
NOW = lambda: strftime("%Y-%m-%d %H:%M:%S")


class TodoStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"


@db.database_registry(DB_PATH, table_name=TABLE, key_field="id")
class TodoItem(BaseModel):
    id: int | None = None
    title: str = db_field(index=True)
    description: str = db_field(default="")
    status: TodoStatus = db_field(default=TodoStatus.PENDING.value)
    created_at: str = db_field(default_factory=NOW)
    updated_at: str = db_field(default_factory=NOW)


@cli.register(name="add", description="Create a todo item")
@cli.argument("title", type=str, help="Todo title")
@cli.argument("description", type=str, default="", help="Todo description")
@cli.option("--add")
@cli.option("-a")
def add_todo(title: str, description: str = "") -> str:
    todo = TodoItem(title=title, description=description)
    todo.save()
    return f"Added: {todo.title} (ID: {todo.id})"


@cli.register(name="list", description="List todo items")
@cli.option("--list")
@cli.option("-l")
def list_todos() -> str:
    todos = TodoItem.objects.all()
    if not todos:
        return "No todo items found."
    return "\n".join(f"{t.id}: {t.title} [{t.status}]" for t in todos)


@cli.register(name="complete", description="Mark a todo item as completed")
@cli.argument("todo_id", type=int, help="Todo ID")
@cli.option("--complete")
@cli.option("-c")
def complete_todo(todo_id: int) -> str:
    todo = TodoItem.objects.get(id=todo_id)
    if not todo:
        return f"Todo item with ID {todo_id} not found."

    todo.status = TodoStatus.COMPLETED.value
    todo.updated_at = NOW()
    todo.save()
    return f"Completed todo ID {todo_id}."


@cli.register(name="update", description="Update a todo item")
@cli.argument("todo_id", type=int, help="Todo ID")
@cli.argument("title", type=str, default=None, help="New title")
@cli.argument("description", type=str, default=None, help="New description")
@cli.option("--update")
@cli.option("-u")
def update_todo(todo_id: int, title: str | None = None, description: str | None = None) -> str:
    todo = TodoItem.objects.get(id=todo_id)
    if not todo:
        return f"Todo item with ID {todo_id} not found."

    if title is not None:
        todo.title = title
    if description is not None:
        todo.description = description

    todo.updated_at = NOW()
    todo.save()
    return f"Updated todo ID {todo_id}."


if __name__ == "__main__":
    cli.run(
        shell_title="Todo Console",
        shell_description="Manage tasks.",
        shell_colors=None,  # auto
        shell_banner=True,
    )
```

Run it as follows:

```bash
# Add
python todo.py add "Buy groceries" "Milk, eggs, bread"
python todo.py --add "Buy groceries" "Milk, eggs, bread"
python todo.py -a "Buy groceries" "Milk, eggs, bread"
python todo.py add --title "Buy groceries" --description "Milk, eggs, bread"

# List
python todo.py list
python todo.py --list
python todo.py -l

# Complete
python todo.py complete 1
python todo.py --complete 1
python todo.py -c 1

# Update
python todo.py update 1 "Read two books" "Finish both novels this week"
python todo.py update 1 --title "Read two books" --description "Finish both novels this week"
python todo.py --update 1 --title "Read two books"
```

Or:

```bash
# Run directly for interactive mode
python todo.py
```
Interactive mode:

```bash
  ______          __         ______                       __   
 /_  __/___  ____/ /___     / ____/___  ____  _________  / /__ 
  / / / __ \/ __  / __ \   / /   / __ \/ __ \/ ___/ __ \/ / _ \
 / / / /_/ / /_/ / /_/ /  / /___/ /_/ / / / (__  ) /_/ / /  __/
/_/  \____/\__,_/\____/   \____/\____/_/ /_/____/\____/_/\___/
Todo Console
Manage tasks.

> help
Shell builtins
  help            Show this menu
  help <command>  Show detailed help for a specific command
  commands        List all registered commands
  exit / quit     Leave interactive mode

Registered commands
  add          Add a new todo item
  delete       Delete a todo item
  list         List all todo items
  complete     Mark a todo item as completed
  update       Update a todo item
  greet        Greet someone by name
  create_user  Create and persist a new user
  list-users   List all persisted users
  get-user     Get a user by ID

Tip: run 'help <command>' for full argument details.
> help add
add
  Add a new todo item

  Usage    usage: test.py add <title> [<description> | --description VALUE]
  Aliases  --add, -a

Arguments
  title  (str, required)                    Title of the todo item
  description  (str, optional, default='')  Description of the todo item
> exit

Goodbye.
```

## Command Decorators

### `@register(...)`

Finalizes a function as a command.

```python
@cli.register(name="add", description="Add a todo")
```

- `name` is optional.
- If `name` is omitted, the command name is inferred from the first long option
  (`--add` -> `add`).
- If no long option exists, it falls back to the function name.

### `@argument(...)`

Defines command argument metadata.

```python
@cli.argument("title", type=str, help="Todo title")
@cli.argument("description", type=str, default="")
```

- Explicit `@argument` declarations are authoritative for ordering/type/help.
- Any function params without `@argument` still work via annotation/default
  inference.

### `@option(...)`

Adds command aliases.

```python
@cli.option("--add")
@cli.option("-a")
```

These aliases are valid for the command token:

```bash
python todo.py add "Buy groceries"
python todo.py --add "Buy groceries"
python todo.py -a "Buy groceries"
```

## Parsing Behavior

For non-boolean arguments, both positional and named forms are supported:

```bash
python todo.py add "Read a book" "Start to finish"
python todo.py add --title "Read a book" --description "Start to finish"
python todo.py add "Read a book" --description "Start to finish"
```

Boolean arguments are flag-style:

```bash
python app.py run --verbose
```

If the same argument is passed twice with different values, parsing fails.

## Command Help Details

Both CLI mode and interactive mode support `help <command>`.

This view includes:

- What the command does
- Invocation tokens (command name + aliases)
- Handler name
- Usage line
- Per-argument requirement, type, defaults, and accepted forms

Example:

```bash
python todo.py help add
```

```text
add
  Add a new todo item

  Usage    usage: test.py add <title> [<description> | --description VALUE]
  Aliases  --add, -a

Arguments
  title  (str, required)                    Title of the todo item
  description  (str, optional, default='')  Description of the todo item
> 
```

## Runtime Helpers

- `cli.run(argv=None, print_result=True)` executes the default module registry.
- `cli.run(...)` also accepts shell controls:
  `shell_prompt`, `shell_title`, `shell_description`, `shell_banner`,
  `shell_colors`, and `shell_input_fn`.
- `cli.run_shell(...)` starts an interactive REPL for the default module registry.
- `cli.list_commands()` prints registered commands and aliases.
- `cli.reset_registry()` clears registry state (useful in tests).
- Built-in help command is always available: `help`, `--help`, and `-h`.

## Interactive Mode

When your app runs with no command-line arguments in an interactive terminal,
`cli.run()` starts an interactive shell by default. In non-interactive contexts
(for example CI or piped stdin), `cli.run()` still prints the normal help menu.

You can force interactive mode explicitly:

```bash
python todo.py --interactive
python todo.py -i
```

`run()` now also accepts shell configuration so one entrypoint can handle both
CLI argument mode and interactive mode:

```python
cli.run(
    shell_prompt="> ",
    shell_title="Todo Console",
    shell_description="Manage tasks and users.",
    shell_banner=True,
    shell_colors=None,  # auto
)
```

You can also call the shell directly:

```python
if __name__ == "__main__":
    cli.run_shell()
```

`run_shell()` supports banner and color controls:

```python
cli.run_shell(
    prompt="> ",
    banner=True,
    shell_title="Todo Console",
    shell_description="Manage tasks and users.",
    colors=None,  # auto
)
```

`banner_text=...` is still accepted as a legacy alias for `shell_title`.

For Figlet-style ASCII banners, install `pyfiglet`:

```bash
pip install pyfiglet
```

Shell-local commands:

- `help`
- `help <command>`
- `commands`
- `exit`
- `quit`

Example:

```text
$ python todo.py
   ____                          __            ________    ____
  / __ \___  _________  ______ _/ /____  _____/ ____/ /   /  _/
 / / / / _ \/ ___/ __ \/ ___/ __/ ___/ |/_/ / /   / /    / /
/ /_/ /  __/ /__/ /_/ / /  / /_(__  )>  </ / /___/ /____/ /
\____/\___/\___/\____/_/   \__/____/_/|_|  \____/_____/___/
Interactive Shell
Type 'help' for shell help and 'exit' to quit.
> help
Interactive Help
================

Shell Commands
  help            Show this menu
  help <command>  Show detailed help for one command
  commands        List available commands
  exit | quit     Leave interactive mode

Registered Commands
  add   Create a todo item
        Aliases: --add, -a
  list  List todo items
        Aliases: --list, -l

Tip: run 'help <command>' for argument-level details.
> help add
Command: add
============
Description: Create a todo item
Usage: usage: todo.py add <title> [<description> | --description VALUE]
Aliases: --add, -a

Arguments
  title (str, required)
    Todo title
    Accepted: <title> or --title VALUE
  description (str, optional, default='')
    Todo description
    Accepted: <description> or --description VALUE
> add "Buy milk"
Added: Buy milk (ID: 1)
> quit
```

## Error Handling

- Unknown command: prints suggestion when available and exits with status `2`.
- Parse errors: prints a specific error + command usage and exits with status `2`.
- Handler crashes: wrapped as `CommandExecutionError` with exception chaining.


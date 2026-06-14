"""Static shell completion snippets."""

from __future__ import annotations


COMMANDS = [
    "init",
    "quickstart",
    "doctor",
    "validate-config",
    "config-upgrade",
    "list-options",
    "list-companies",
    "enable-company",
    "list-presets",
    "update-presets",
    "use-preset",
    "schema",
    "completions",
    "run",
    "uninstall-data",
]

SOURCES = ["sample", "local_file", "remoteok", "arbeitnow", "greenhouse", "lever", "ashby", "workday"]


def render_completion(shell: str) -> str:
    if shell == "bash":
        return bash_completion()
    if shell == "zsh":
        return zsh_completion()
    if shell == "fish":
        return fish_completion()
    raise ValueError(f"Unsupported shell: {shell}")


def bash_completion() -> str:
    commands = " ".join(COMMANDS)
    sources = " ".join(SOURCES)
    return f"""_labor_sieve()
{{
  local cur prev
  COMPREPLY=()
  cur="${{COMP_WORDS[COMP_CWORD]}}"
  prev="${{COMP_WORDS[COMP_CWORD-1]}}"
  case "$prev" in
    --source)
      COMPREPLY=( $(compgen -W "{sources}" -- "$cur") )
      return 0
      ;;
    completions)
      COMPREPLY=( $(compgen -W "bash zsh fish" -- "$cur") )
      return 0
      ;;
  esac
  if [[ $COMP_CWORD -eq 1 ]]; then
    COMPREPLY=( $(compgen -W "{commands}" -- "$cur") )
  fi
}}
complete -F _labor_sieve labor-sieve
"""


def zsh_completion() -> str:
    commands = " ".join(COMMANDS)
    sources = " ".join(SOURCES)
    return f"""#compdef labor-sieve
_labor_sieve() {{
  local -a commands sources
  commands=({commands})
  sources=({sources})
  if (( CURRENT == 2 )); then
    _describe 'command' commands
  elif [[ $words[CURRENT-1] == --source ]]; then
    _describe 'source' sources
  elif [[ $words[2] == completions ]]; then
    _values 'shell' bash zsh fish
  fi
}}
_labor_sieve "$@"
"""


def fish_completion() -> str:
    lines = ["complete -c labor-sieve -f"]
    for command in COMMANDS:
        lines.append(f"complete -c labor-sieve -n '__fish_use_subcommand' -a {command}")
    for source in SOURCES:
        lines.append(f"complete -c labor-sieve -l source -a {source}")
    lines.append("complete -c labor-sieve -n '__fish_seen_subcommand_from completions' -a 'bash zsh fish'")
    return "\n".join(lines) + "\n"

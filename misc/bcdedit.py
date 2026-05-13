"""jc - JSON Convert `bcdedit /enum firmware` command output parser

Parses the output of `bcdedit /enum firmware` on Windows to produce a list
of firmware boot entries (UEFI boot manager entries).

Usage (cli):

    $ bcdedit /enum firmware | jc --bcdedit-firmware

Usage (module):

    import jc
    result = jc.parse('bcdedit_firmware', bcdedit_command_output)

Schema:

    [
      {
        "identifier":          string,
        "description":         string,
        "type":                string,         # "Firmware Boot Manager",
                                               # "Windows Boot Manager",
                                               # "Firmware Application",
                                               # or the raw header text
        "device":              string/null,
        "path":                string/null,
        "displayorder":        [string],       # only on {fwbootmgr}
        "bootsequence":        [string],       # only on {fwbootmgr}
        "timeout":             integer/null,
        "locale":              string/null,
        "inherit":             string/null,
        "default":             string/null,
        "resumeobject":        string/null,
        "<other_key>":         string          # any other key bcdedit emits
      }
    ]

    All keys are normalized to lowercase, with spaces removed
    (e.g. "Boot Sequence" -> "bootsequence"). Multi-value fields like
    `displayorder` and `bootsequence` come back as lists of GUID strings.

Examples:

    $ bcdedit /enum firmware | jc --bcdedit-firmware -p
    [
      {
        "identifier": "{fwbootmgr}",
        "type": "Firmware Boot Manager",
        "description": "Firmware Boot Manager",
        "displayorder": [
          "{bootmgr}",
          "{0bb887d3-78d2-11ee-9b3a-806e6f6e6963}"
        ],
        "timeout": 1
      },
      {
        "identifier": "{bootmgr}",
        "type": "Windows Boot Manager",
        "device": "partition=\\Device\\HarddiskVolume1",
        "path": "\\EFI\\Microsoft\\Boot\\bootmgfw.efi",
        "description": "Windows Boot Manager"
      }
    ]
"""
import re
from typing import List, Dict, Any, Optional


class info:
    """Provides parser metadata (version, author, etc.)"""
    version = '1.0'
    description = '`bcdedit /enum firmware` command parser'
    author = 'Your Name'
    author_email = 'you@example.com'
    compatible = ['win32']
    magic_commands = ['bcdedit /enum firmware']
    tags = ['command']


__version__ = info.version


# Keys whose values are GUID-like tokens that may span multiple lines
# (bcdedit indents continuation lines for these).
_LIST_KEYS = {'displayorder', 'bootsequence', 'toolsdisplayorder'}

# Keys that should be coerced to int when possible.
_INT_KEYS = {'timeout'}

_GUID_RE = re.compile(r'\{[0-9a-fA-F-]+\}|\{[a-zA-Z]+\}')


def _normalize_key(raw: str) -> str:
    """Lowercase and strip whitespace from a bcdedit field name."""
    return re.sub(r'\s+', '', raw).lower()


def _parse_block(block: str) -> Optional[Dict[str, Any]]:
    """Parse a single bcdedit entry block into a dict, or None if empty."""
    lines = [ln for ln in block.splitlines() if ln.strip()]
    if len(lines) < 2:
        return None

    # First non-blank line is the human-readable type header
    # (e.g. "Windows Boot Manager", "Firmware Application (101fffff)").
    # The second is a separator of dashes; skip it.
    type_header = lines[0].strip()
    body = [ln for ln in lines[1:] if not set(ln.strip()) <= {'-'}]

    entry: Dict[str, Any] = {'type': type_header}
    current_key: Optional[str] = None

    for line in body:
        # A new key/value pair: a non-indented word, then whitespace, then value.
        # Continuation lines for list-valued keys are indented.
        m = re.match(r'^(\S[^\s]*)\s+(.*\S)\s*$', line)
        if m and not line.startswith((' ', '\t')):
            key = _normalize_key(m.group(1))
            value = m.group(2).strip()
            current_key = key

            if key in _LIST_KEYS:
                entry[key] = _GUID_RE.findall(value) or [value]
            elif key in _INT_KEYS:
                try:
                    entry[key] = int(value)
                except ValueError:
                    entry[key] = value
            else:
                entry[key] = value
        elif current_key and current_key in _LIST_KEYS:
            # Continuation of a list-valued key
            entry[current_key].extend(_GUID_RE.findall(line))
        # Anything else we silently skip; raw mode preserves the original text.

    return entry


def _process(proc_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Final, schema-conformant processing of the raw parsed data."""
    # Promote `identifier` to a top-level field if present, and ensure a
    # consistent key order: identifier, type, description, then the rest.
    out = []
    for entry in proc_data:
        ordered: Dict[str, Any] = {}
        for k in ('identifier', 'type', 'description'):
            if k in entry:
                ordered[k] = entry[k]
        for k, v in entry.items():
            if k not in ordered:
                ordered[k] = v
        out.append(ordered)
    return out


def parse(
    data: str,
    raw: bool = False,
    quiet: bool = False,
) -> List[Dict[str, Any]]:
    """Main parse function.

    Parameters:

        data:   (string)  text data to parse
        raw:    (boolean) unprocessed output if True
        quiet:  (boolean) suppress warning messages if True

    Returns:

        List of Dictionaries. Raw or processed structured data.
    """
    # jc convention: callers can verify the runtime is supported.
    # We don't hard-fail here because the parser itself is portable;
    # the *command* is Windows-only.

    raw_output: List[Dict[str, Any]] = []

    if data:
        # Normalize line endings, then split on blank-line boundaries.
        normalized = data.replace('\r\n', '\n').replace('\r', '\n')
        blocks = re.split(r'\n{2,}', normalized.strip())

        for block in blocks:
            entry = _parse_block(block)
            if entry is not None:
                raw_output.append(entry)

    return raw_output if raw else _process(raw_output)

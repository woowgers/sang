#!/usr/bin/env nu

def os_name []: nothing -> string {
  return $nu.os-info.name
}


def restart []: nothing -> nothing {
  let os = os_name 
  match $os {
    "linux" => {systemctl reboot}
    "windows" => {shutdown /r /t 0}
  }
}


def restart_to_uefi []: nothing -> nothing {
  let os = os_name 
  match $os {
    "linux" => {systemctl reboot --firmware-setup}
    "windows" => {shutdown /r /fw /t 0}
  }
}


def load_to_uefi []: nothing -> nothing {
  let confirm = (
      zenity --question
          --title="Reboot to UEFI"
          --text="Reboot now into UEFI firmware setup?"
          --width=350
      | complete
  )

  if $confirm.exit_code == 0 {
    restart_to_uefi
  }
}


def set_next_entry [
    id: string
] {
  let os = os_name
  match $os {
    "linux" => { return (pkexec efibootmgr -n $id | complete) }
    "windows" => { return (gsudo bcdedit /set "{fwbootmgr}" bootsequence $id | complete) }
  }
}


def pick_and_load [
    id: string
    entries: table<id: string, name: string>
] {
  let name = ($entries | where id == $id | get name.0)

  let result = set_next_entry $id
  if $result == null {
      zenity --error --text=$"Failed to set BootNext for ($id) - empty result ($entries) ($name) ($result)"
      exit 1
  }

  if $result.exit_code != 0 {
      zenity --error --text=$"Failed to set BootNext for ($id):\n($result.stderr)" --width=350
      exit 1
  }

  let confirm = (
      zenity --question
          --title="Boot Next Set"
          --text=$"Next boot will be: <b>($name)</b>\n\nReboot now?"
          --width=350
      | complete
  )

  if $confirm.exit_code == 0 {
    restart
  }
}


def list_boot_entries []: nothing -> table {
  let os = os_name
  match $os {
    "linux" => {
      return (
        pkexec efibootmgr
        | jc --efibootmgr
        | jq '.boot_options[] | {name: .display_name, id: (.boot_option_reference | gsub("Boot"; ""))}'
        | jq -s
        | from json
      )
    }
    "windows" => {
      return (
        gsudo bcdedit /enum firmware
        | jc --bcdedit
        | jq '.[] | {name: .description, id: .identifier}'
        | jq -s
        | from json
        | where id != '{fwbootmgr}'
      )
    } }
}


def main [] {
    let entries = list_boot_entries

    if ($entries | is-empty) {
        zenity --error --text="No active UEFI boot entries found." --width=300
        exit 1
    }

    let display_entries = (
        [[id name]; ["__firmware__" "⚙ UEFI Firmware Setup"]]
        | append $entries
    )

    let zenity_args = ($display_entries | get name)

    let selected = (
        zenity --list --title="Select Next Boot" ...$zenity_args
        | complete
    )

    if $selected.exit_code != 0 or ($selected.stdout | str trim | is-empty) {
        exit 0
    }
    let name = ($selected.stdout | str trim)
    let id = ($entries | where name == $name | get id.0)

    if $id == "__firmware__" {
      load_to_uefi
    } else {
      pick_and_load $id $entries
    }
}

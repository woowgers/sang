#!/usr/bin/env nu


def os_family []: nothing -> string {
  return ($nu).os-info.name
}


def restart []: nothing -> nothing {
  let os = os_family 
  match $os {
    "linux" => {systemctl reboot}
    "windows" => {shutdown /r /t 0}
  }
}


def restart_to_uefi []: nothing -> nothing {
  let os = os_family 
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


def pick_and_load [
    id: string
    entries: table<id: string, name: string>
] {
  let name = ($entries | where id == $id | get name.0)

  let result = (pkexec /usr/bin/efibootmgr -n $id | complete)
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
  let os = os_family
  match $os {
    "linux" => {
      return (
        efibootmgr
        | jc --efibootmgr
        | jq '.boot_options[] | {name: .display_name, id: (.boot_option_reference | gsub("Boot"; ""))}'
        | jq -s
        | from json
      )
    }
    "windows" => {
      return (

      )
    }
  }
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

    let zenity_args = ($display_entries | each {|e| [$e.id, $e.name]} | flatten)

    let selected = (
        zenity --list
            --title="Select Next Boot"
            --text="Choose what to boot next:"
            --column="ID" --column="Boot Entry"
            --hide-column=1 --print-column=1
            --width=400 --height=350
            ...$zenity_args
        | complete
    )

    if $selected.exit_code != 0 or ($selected.stdout | str trim | is-empty) {
        exit 0
    }

    let id = ($selected.stdout | str trim)

    if $id == "__firmware__" {
      load_to_uefi
    } else {
      pick_and_load $id $entries
    }
}

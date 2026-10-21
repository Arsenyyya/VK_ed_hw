-- Display a real command in Terminal, then return that window's ID.
on run argv
    set mode to item 1 of argv
    set projectPath to item 2 of argv
    set taskCommand to "cd " & quoted form of projectPath & " && clear && .venv/bin/python scripts/status.py " & mode
    tell application "Terminal"
        activate
        set targetTab to do script taskCommand
        set custom title of targetTab to "Frontend · RustFS / MapReduce"
        set font name of targetTab to "Menlo"
        set font size of targetTab to 14
        set background color of targetTab to {5000, 6500, 9000}
        set normal text color of targetTab to {60000, 62000, 64000}
        if mode is "verification" then
            set bounds of front window to {55, 40, 1055, 440}
        else
            set bounds of front window to {55, 40, 1055, 560}
        end if
        delay 4
        return id of front window
    end tell
end run

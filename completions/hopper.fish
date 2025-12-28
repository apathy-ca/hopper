# Fish completion for Hopper CLI
# Save to ~/.config/fish/completions/hopper.fish

function __fish_hopper_needs_command
    set -l cmd (commandline -opc)
    if test (count $cmd) -eq 1
        return 0
    end
    return 1
end

function __fish_hopper_using_command
    set -l cmd (commandline -opc)
    if test (count $cmd) -gt 1
        if test $argv[1] = $cmd[2]
            return 0
        end
    end
    return 1
end

# Main commands
complete -c hopper -n __fish_hopper_needs_command -a task -d 'Manage tasks'
complete -c hopper -n __fish_hopper_needs_command -a project -d 'Manage projects'
complete -c hopper -n __fish_hopper_needs_command -a instance -d 'Manage instances'
complete -c hopper -n __fish_hopper_needs_command -a config -d 'Manage configuration'
complete -c hopper -n __fish_hopper_needs_command -a auth -d 'Manage authentication'
complete -c hopper -n __fish_hopper_needs_command -a server -d 'Manage server'
complete -c hopper -n __fish_hopper_needs_command -a init -d 'Initialize configuration'

# Shortcuts
complete -c hopper -n __fish_hopper_needs_command -a add -d 'Quick add task'
complete -c hopper -n __fish_hopper_needs_command -a ls -d 'Quick list tasks'

# Task subcommands
complete -c hopper -n '__fish_hopper_using_command task' -a 'add list get update status delete search'

# Project subcommands
complete -c hopper -n '__fish_hopper_using_command project' -a 'create list get update delete tasks'

# Instance subcommands
complete -c hopper -n '__fish_hopper_using_command instance' -a 'create list get tree start stop status'

# Config subcommands
complete -c hopper -n '__fish_hopper_using_command config' -a 'get set list'

# Auth subcommands
complete -c hopper -n '__fish_hopper_using_command auth' -a 'login logout status'

# Server subcommands
complete -c hopper -n '__fish_hopper_using_command server' -a 'start stop status logs'

# Global options
complete -c hopper -s c -l config -d 'Configuration file path'
complete -c hopper -s v -l verbose -d 'Enable verbose output'
complete -c hopper -l json -d 'Output in JSON format'
complete -c hopper -l version -d 'Show version'
complete -c hopper -l help -d 'Show help'

# Task options
complete -c hopper -n '__fish_hopper_using_command task' -s d -l description -d 'Task description'
complete -c hopper -n '__fish_hopper_using_command task' -s p -l priority -a 'low medium high urgent'
complete -c hopper -n '__fish_hopper_using_command task' -s t -l tag -d 'Add tag'
complete -c hopper -n '__fish_hopper_using_command task' -l project -d 'Project ID'
complete -c hopper -n '__fish_hopper_using_command task' -l status -a 'open in_progress blocked completed cancelled'

# Instance options
complete -c hopper -n '__fish_hopper_using_command instance' -l scope -a 'global project orchestration' -d 'Instance scope'

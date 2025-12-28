#compdef hopper

# Zsh completion for Hopper CLI
# Add to ~/.zshrc:
#   fpath=(~/.hopper/completions $fpath)
#   autoload -Uz compinit && compinit

_hopper_completion() {
    local -a completions
    local -a completions_with_descriptions
    local -a response
    (( ! $+commands[hopper] )) && return 1

    response=("${(@f)$(env COMP_WORDS="${words[*]}" COMP_CWORD=$((CURRENT-1)) _HOPPER_COMPLETE=zsh_complete hopper)}")

    for type_value in $response; do
        type="${type_value%%,*}"
        value="${type_value#*,}"

        if [[ $type == 'plain' ]]; then
            if [[ $value == *$'\t'* ]]; then
                completions_with_descriptions+=("$value")
            else
                completions+=("$value")
            fi
        elif [[ $type == 'dir' ]]; then
            _path_files -/
        elif [[ $type == 'file' ]]; then
            _path_files -f
        fi
    done

    if [ -n "$completions_with_descriptions" ]; then
        _describe -V unsorted completions_with_descriptions
    fi

    if [ -n "$completions" ]; then
        compadd -U -V unsorted -a completions
    fi
}

compdef _hopper_completion hopper

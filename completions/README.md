# Shell Completion for Hopper CLI

Shell completion scripts for Bash, Zsh, and Fish.

## Installation

### Bash

Add to your `~/.bashrc`:

```bash
source /path/to/hopper/completions/hopper.bash
```

Or copy to system completions:

```bash
sudo cp completions/hopper.bash /etc/bash_completion.d/hopper
```

### Zsh

Add completion directory to fpath in `~/.zshrc`:

```zsh
fpath=(~/.hopper/completions $fpath)
autoload -Uz compinit && compinit
```

Then copy the completion file:

```bash
mkdir -p ~/.hopper/completions
cp completions/hopper.zsh ~/.hopper/completions/_hopper
```

### Fish

Copy to Fish completions directory:

```bash
mkdir -p ~/.config/fish/completions
cp completions/hopper.fish ~/.config/fish/completions/
```

## Usage

After installation, you can use Tab completion:

```bash
# Command completion
hopper <TAB>

# Subcommand completion
hopper task <TAB>

# Option completion
hopper task add --<TAB>

# Argument completion
hopper task status abc123 <TAB>
```

## Testing

Test completions work:

```bash
# Bash
source completions/hopper.bash
hopper <TAB><TAB>

# Zsh
source completions/hopper.zsh
hopper <TAB>

# Fish
source completions/hopper.fish
hopper <TAB>
```

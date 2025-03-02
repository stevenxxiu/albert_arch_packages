# Albert Launcher Arch Linux Packages Search Extension
Query *Arch Linux*'s official packages and *AUR* packages.

## Install
To install, copy or symlink this directory to `~/.local/share/albert/python/plugins/arch_linux_packages/`.

## Development Setup
To setup the project for development, run:

    $ cd arch_linux_packages/
    $ pre-commit install --hook-type pre-commit --hook-type commit-msg
    $ mkdir stubs/
    $ ln --symbolic ~/.local/share/albert/python/plugins/albert.pyi stubs/

To lint and format files, run:

    $ pre-commit run --all-files

volt-nvim
=========

Voltron integration for Neovim.

**IMPORTANT**: Install voltron manually using the most recent commit at
https://github.com/FredrikAleksander/voltron as it requires features and fixes
that has not yet been merged into https://github.com/snare/voltron

Voltron is a UI toolkit for debuggers. It supports WinDbg/Cdb, GDB and LLDB,
and can display debugger views in the terminal or using a Web interface. It is
not only a great UI toolkit, but also a great API for getting debugger state
in a consistent way across debuggers.

Volt is a plugin for Neovim that acts as a Voltron client, allowing you to
connect to a running Voltron session and see breakpoints and the program
counter within the source code in Neovim.

Requires working Python 3 host in Neovim. Remember to call

```
:UpdateRemotePlugins
:helptags ALL
```

```
:help volt
```

For documentation

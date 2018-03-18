# GDB/LLDB/PyKD Python initscript for volt-nvim
# If environment variable `NVIM_LISTEN_ADDRESS` exists, connect to
# Neovim RPC API and call command `VoltAttach`
# If exit hook is available for current debugger, add a hook to call
# `VoltDetach` on debugger exit
import os


def main():
    import neovim
    nvim = neovim.attach('socket', path=os.environ.get('NVIM_LISTEN_ADDRESS'))
    try:
        nvim.command('VoltAttach')
        try:
            import lldb
            host = 'lldb'
        except:
            pass
        try:
            import gdb
            host = 'gdb'

            class VoltQuit(gdb.Command):
                def __init__(self):
                    super(VoltQuit, self).__init__("volt-quit", gdb.COMMAND_USER)
                def invoke(self, arg, from_tty):
                    nvim.command('VoltDetach')
                    gdb.execute('quit')
            VoltQuit()
        except ImportError:
            pass
        try:
            import pykd
            host = 'windbg'
        except:
            pass
    except:
        pass

if 'NVIM_LISTEN_ADDRESS' in os.environ:
    main()

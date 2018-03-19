import voltron
import neovim
import re
from voltron.core import Client
from os import path
from collections import namedtuple, deque

Breakpoint = namedtuple('Breakpoint', 'id line')
ProgramCounter = namedtuple('ProgramCounter', 'file line')
Target = namedtuple('Target', 'id file arch state')

name_regex = re.compile('^(.*):(\d+)$')

class DebugUI:
    def __init__(self, nvim):
        """

        :type nvim: neovim.api.Nvim

        """
        self.nvim = nvim
        self.bp_base_index = 257
        self.pc_base_index = 357
        self.breakpoints = {}
        self.pc = None
        self.client = Client(build_requests=self.build_requests, 
            callback= self.process_responses)
        self.location_cache = None
        self.targets = None
        self.history = deque(maxlen=64)
    def getlocationbyname(self, location):
        if 'name' in location:
            result = name_regex.match(location['name'])
            if result != None:
                return result.group(1, 2)
        elif 'file' in location and 'line' in location:
            return (location['file'], location['line'])
        return None
    def getlocationbyaddr(self, address):
        if address in self.location_cache:
            return self.location_cache[address]
        loc = None
        try:
            res = self.client.perform_request('source_location', address=address)
            if res.is_success:
                sloc = res.output
                loc = (sloc[0], sloc[1])
        except:
            pass
        self.location_cache[address] = loc
        return loc
    def getlocation(self, bp):
        r = None
        for loc in bp['locations']:
            if 'name' in loc or 'file' in loc:
                r = self.getlocationbyname(loc)
                if r != None:
                    break
            if 'address' in loc:
                r = self.getlocationbyaddr(loc['address'])
                if r != None:
                    break
        return r
    def process_breakpoint(self, breakpoint):
        if(len(breakpoint['locations']) > 0):
            loc = self.getlocation(breakpoint)
            if loc != None:
                file, line = loc
                return { 'file': file,
                    'id': breakpoint['id'],
                    'line': int(line) }
        return None
    def process_breakpoints(self, breakpoints):
        processed = [self.process_breakpoint(x) for x in breakpoints]
        bps = [x for x in processed if x != None]
        return bps
    def build_requests(self):
        return [self.client.create_request('targets'), 
                self.client.create_request('breakpoints'),
                self.client.create_request('registers', registers=['pc'])]
    def refresh(self):
        targets = self.client.perform_request('targets')
        breakpoints = self.client.perform_request('breakpoints')
        registers = self.client.perform_request('registers', registers=['pc'])
        self.process_responses([targets, breakpoints, registers])
    def process_responses(self, results,  **kwargs):
        bps = []
        pc = None
        if results[0].status == 'success':
            self.targets = results[0].targets
            if len(self.targets) != 1:
                raise Exception('only one debug target supported')
        else:
            self.nvim.async_call(self.update, [], None)
            return
        if results[1].status == 'success':
            try:
                bps = self.process_breakpoints(results[1].breakpoints)
            except:
                pass
        if results[2].status == 'success':
            try:
                regs = results[2].registers
                pcaddress = regs[list(regs.keys())[0]]
                pc = self.getlocationbyaddr(pcaddress)
            except:
                pass
        self.nvim.async_call(self.update, bps, pc)
    def focusfile(self, file, line):
        absfile = path.abspath(file)
        if not path.exists(file):
            return
        bufnr = None
        winnr = None
        for buffer in self.nvim.buffers:
            if buffer.name == absfile:
                bufnr = buffer.number
                break
        if bufnr != None:
            for win in self.nvim.windows:
                if win.buffer.number == bufnr:
                    winnr = win.number
                    break
        if winnr != None:
            self.nvim.command('{} wincmd w'.format(winnr))
        else:
            if self.nvim.current.window.buffer.options['buftype'] != 'terminal':
                winnr = self.nvim.current.window.number
            if winnr == None:
                self.nvim.command('vsp')
                winnr = self.nvim.current.window.number
            self.nvim.command('{} wincmd w'.format(winnr))
            if bufnr != None:
                self.nvim.command('hide buffer {}'.format(bufnr))
            else:
                self.nvim.command('hide e {}'.format(file))
        self.nvim.command('{}'.format(line))
    def isfileopen(self, file):
        return True in (
            x.name == path.abspath(file) for x in self.nvim.buffers)
    def normalizepath(self, p):
        curdir = path.abspath('.')
        ap = path.abspath(p)
        if path.commonprefix([curdir, ap]) == curdir:
            return path.relpath(ap, curdir)
        return ap
    def getbufnr(self, file):
        for b in self.nvim.buffers:
            if b.name == path.abspath(file):
                return b.number
        return None
    def unplace_pc(self, pc):
        bufnr = self.getbufnr(pc.file)
        self.nvim.command('sign unplace {0} buffer={1}'
                .format(self.pc_base_index, bufnr))
    def place_pc(self, pc):
        bufnr = self.getbufnr(pc.file)
        self.nvim.command('sign place {0} line={1} name=voltpcsel buffer={2}'
                .format(self.pc_base_index, pc.line, bufnr))
    def unplace_breakpoints(self, bufnr, bps):
        for bp in bps:
            self.nvim.command('sign unplace {0} buffer={1}'
                    .format(self.bp_base_index + bp.id, bufnr))
    def place_breakpoints(self, bufnr, bps):
        for bp in bps:
            self.nvim.command('sign place {0} line={1} name=voltbp buffer={2}'
                    .format(self.bp_base_index + bp.id, bp.line, bufnr))
    def update_breakpoints(self, bps):
        bp_base = self.bp_base_index
        files = set([self.normalizepath(x['file']) for x in bps]).union(
            self.breakpoints.keys())
        for file in files:
            new_bps = [Breakpoint(id=x['id'], line=x['line']) 
                for i,x in enumerate([x for x in bps if 
                    self.normalizepath(x['file']) == file])]
            if self.isfileopen(file):
                bufnr = self.getbufnr(file)
                if self.breakpoints.__contains__(file):
                    self.unplace_breakpoints(bufnr, self.breakpoints[file])
                for bp in new_bps:
                    self.place_breakpoints(bufnr, new_bps)
            self.breakpoints[file] = new_bps
    def update_pc(self, pc):
        if self.pc != None and self.isfileopen(self.pc.file):
            self.unplace_pc(self.pc)
        if pc != None:
            self.focusfile(pc.file, pc.line)
            if self.isfileopen(pc.file):
                self.place_pc(pc)
        self.pc = pc

    def update(self, bps, pc):
        self.update_breakpoints(bps)
        self.update_pc(None if pc == None else ProgramCounter(file=pc[0], line=pc[1]))

    def breakpoint_toggle(self, file, line):
        host = self.gethost()
        bps = None
        npath = self.normalizepath(file)

        if npath in self.breakpoints:
            bps = [x for x in self.breakpoints[npath] if x.line == line]
            #raise Exception(repr(bps))
            if len(bps) < 1:
                bps = None

        if bps is None:
            if host == 'lldb':
                self.execute('breakpoint set -l {} -f "{}"'.format(line, npath))
            elif host == 'gdb':
                self.execute('break {}:{}'.format(npath, line))
            elif host == 'windbg':
                self.execute('bp `{}:{}`'.format(npath, line))
        else:
            for x in bps:
                if host == 'lldb':
                    self.execute('breakpoint delete {}'.format(x.id))
                elif host == 'gdb':
                    self.execute('delete {}'.format(x.id))
                elif host == 'windbg':
                    self.execute('bc [{}]'.format(x.id))
        self.refresh()


    def execute(self, command):
        res = self.client.perform_request('command', command=command)
        if res.status == 'success':
            return res.output or ''
        raise Exception(res.message)

    def gethostversion(self):
        try:
            res = self.client.perform_request('version')
            if res.status == 'success':
                return res.host_version
        except:
            pass
        return ''

    def gethost(self):
        ver = self.gethostversion()
        if ver.startswith('GNU gdb'):
            return 'gdb'
        if ver.find('lldb') != -1:
            return 'lldb'
        if ver.find('Microsoft (R) Windows Debugger Version') != -1:
            return 'windbg'
        if ver == '':
            return ''
        return 'unknown'

    def continue_execution(self):
        host = self.gethost()
        if host == 'lldb':
            self.execute('continue')
        elif host == 'gdb':
            self.execute('continue')
        elif host == 'windbg':
            self.execute('g')
        self.refresh()
    
    def stepinto(self):
        host = self.gethost()
        if host == 'lldb':
            self.execute('step')
        elif host == 'gdb':
            self.execute('step')
        elif host == 'windbg':
            pass
        self.refresh()

    def stepintoi(self):
        host = self.gethost()
        if host == 'lldb':
            self.execute('si')
        elif host == 'gdb':
            self.execute('si')
        elif host == 'windbg':
            pass
        self.refresh()

    def stepover(self):
        host = self.gethost()
        if host == 'lldb':
            self.execute('next')
        elif host == 'gdb':
            self.execute('next')
        elif host == 'windbg':
            pass
        self.refresh()

    def stepoveri(self):
        host = self.gethost()
        if host == 'lldb':
            self.execute('ni')
        elif host == 'gdb':
            self.execute('ni')
        elif host == 'windbg':
            pass
        self.refresh()

    def stepout(self):
        host = self.gethost()
        if host == 'lldb':
            self.execute('finish')
        elif host == 'gdb':
            self.execute('finish')
        elif host == 'windbg':
            pass
        self.refresh()

    def start(self):
        self.location_cache = {}
        self.client.start()

    def stop(self):
        self.nvim.async_call(self.update, [], None)
        self.client.stop()

@neovim.plugin
class VoltronPlugin:
    def __init__(self, nvim):
        """

        :type nvim: neovim.api.Nvim
        
        """
        self.nvim = nvim
        self.debugui = DebugUI(nvim)

    @neovim.command('VoltView', nargs='1', sync=True)
    def view(self, args):
        self.nvim.command('terminal voltron view {0}'.format(args[0]))

    @neovim.command('VoltLaunch')
    def launch(self):
        if self.debugui.gethost() == '' and 'debug_launch' in self.nvim.vars:
            self.nvim.command('call {}()'.format(self.nvim.vars['debug_launch']))

    @neovim.command('VoltQuit')
    def quit(self):
        if self.debugui.gethost() != '' and 'debug_quit' in self.nvim.vars:
            self.nvim.command('call {}()'.format(self.nvim.vars['debug_quit']))

    @neovim.command('VoltAttach', nargs='*')
    def attach(self, args):
        self.debugui.start()

    @neovim.command('VoltDetach')
    def detach(self):
        self.debugui.stop()

    @neovim.function('VoltHostVersion', sync=True)
    def host(self, args):
        return self.debugui.gethostversion()

    @neovim.function('VoltCommand', sync=True)
    def command(self, args):
        if len(args) != 1:
            raise Exception('Invalid number of arguments, expected 1')
        return self.debugui.execute(args[0])

    @neovim.command('VoltBreakpointToggle', sync=True)
    def breakpoint_toggle(self):
        row, col = self.nvim.current.window.cursor
        return self.debugui.breakpoint_toggle(self.nvim.current.buffer.name,
                row)

    @neovim.command('VoltRefresh', sync=True)
    def refresh(self):
        self.debugui.refresh()

    @neovim.command('VoltContinue', sync=True)
    def continue_execution(self):
        self.debugui.continue_execution()

    @neovim.command('VoltStepInto', sync=True)
    def stepinto(self):
        self.debugui.stepinto()

    @neovim.command('VoltStepOver', sync=True)
    def stepover(self):
        self.debugui.stepover()

    @neovim.command('VoltStepOut', sync=True)
    def stepout(self):
        self.debugui.stepout()

    @neovim.command('VoltStepIntoI', sync=True)
    def stepintoi(self):
        self.debugui.stepintoi()

    @neovim.command('VoltStepOverI', sync=True)
    def stepoveri(self):
        self.debugui.stepoveri()

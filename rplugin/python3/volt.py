import voltron
import neovim
import re
from voltron.core import Client
from os import path
from collections import namedtuple

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
    def getlocationbyname(self, location):
        print(location)
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
                    'line': line }
        return None
    def process_breakpoints(self, breakpoints):
        processed = [self.process_breakpoint(x) for x in breakpoints]
        bps = [x for x in processed if x != None]
        return bps
    def build_requests(self):
        return [self.client.create_request('targets'), 
                self.client.create_request('breakpoints'),
                self.client.create_request('registers', registers=['pc'])]
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
                    .format(bp.id, bufnr))
    def place_breakpoints(self, bufnr, bps):
        for bp in bps:
            self.nvim.command('sign place {0} line={1} name=voltbp buffer={2}'
                    .format(bp.id, bp.line, bufnr))
    def update_breakpoints(self, bps):
        print(bps)
        bp_base = self.bp_base_index
        files = set([self.normalizepath(x['file']) for x in bps]).union(
            self.breakpoints.keys())
        for file in files:
            print(file)
            new_bps = [Breakpoint(id=bp_base+i, line=x['line']) 
                for i,x in enumerate([x for x in bps if 
                    self.normalizepath(x['file']) == file])]
            if self.isfileopen(file):
                print(file)
                bufnr = self.getbufnr(file)
                if self.breakpoints.__contains__(file):
                    self.unplace_breakpoints(bufnr, self.breakpoints[file])
                for bp in new_bps:
                    self.place_breakpoints(bufnr, new_bps)
            self.breakpoints[file] = new_bps
    def update_pc(self, pc):
        # TODO: Open and focus file containing PC
        if self.pc != None and self.isfileopen(self.pc.file):
            self.unplace_pc(self.pc)
        if pc != None and self.isfileopen(pc.file):
            self.place_pc(pc)
        self.pc = pc
    def update(self, bps, pc):
        self.update_breakpoints(bps)
        self.update_pc(None if pc == None else ProgramCounter(file=pc[0], line=pc[1]))
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
        # TODO: Support arguments for Voltron specifying connection info
        self.nvim.command('terminal voltron view {0}'.format(args[0]))

    @neovim.command('VoltAttach', nargs='*')
    def attach(self, args):
        self.debugui.start()

    @neovim.command('VoltDetach')
    def detach(self):
        self.debugui.stop()

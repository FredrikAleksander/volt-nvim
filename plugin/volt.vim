if !exists('g:volt#sign#bp_symbol')
	let g:volt#sign#bp_symbol = 'B>'
endif

if !exists('g:volt#sign#pc_symbol')
	let g:volt#sign#pc_symbol = '->'
endif

exe 'sign define voltbp text=' . g:volt#sign#bp_symbol . ' texthl=VoltBreakpointSign linehl=VoltBreakpointLine'
exe 'sign define voltpcsel text=' . g:volt#sign#pc_symbol . ' texthl=VoltSelectedPCSign linehl=VoltSelectedPCLine'
exe 'sign define voltpcunsel text=' . g:volt#sign#pc_symbol . ' texthl=VoltUnselectedPCSign linehl=VoltUnselectedPCLine'


#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit('Usage: prepare_three_houses_one_time_submit.py <source-root>')

root = Path(sys.argv[1])
path = root / 'src/Ryujinx.Graphics.Vulkan/CommandBufferPool.cs'
text = path.read_text(encoding='utf-8').replace('\r\n', '\n')
old = '''                        var commandBufferBeginInfo = new CommandBufferBeginInfo
                        {
                            SType = StructureType.CommandBufferBeginInfo,
                        };
'''
new = '''                        var commandBufferBeginInfo = new CommandBufferBeginInfo
                        {
                            SType = StructureType.CommandBufferBeginInfo,
                            // MoltenVK prefill modes only remain effective across reused
                            // primary command buffers when each recording is explicitly
                            // marked as a one-time submission. Ryujinx resets and records
                            // these buffers anew for every submission, so this accurately
                            // describes their lifetime and prevents later recordings from
                            // falling back to the largest-footprint deferred encoding path.
                            Flags = CommandBufferUsageFlags.OneTimeSubmitBit,
                        };
'''
if text.count(old) != 1:
    raise SystemExit(f'Expected one command-buffer begin block, found {text.count(old)}')
path.write_text(text.replace(old, new, 1), encoding='utf-8')

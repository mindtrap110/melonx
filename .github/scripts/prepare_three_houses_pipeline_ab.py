#!/usr/bin/env python3

from pathlib import Path
import sys


def exact_replace(text: str, old: str, new: str, description: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Expected exactly one {description}, found {count}.")
    return text.replace(old, new, 1)


if len(sys.argv) != 3:
    raise SystemExit("Usage: prepare_three_houses_pipeline_ab.py <source-root> <sparse|throttle>")

root = Path(sys.argv[1])
mode = sys.argv[2]

if mode not in {"sparse", "throttle"}:
    raise SystemExit(f"Unknown mode: {mode}")

throttle_ms = 4 if mode == "throttle" else 0
path = root / "src/Ryujinx.Graphics.Vulkan/PipelineBase.cs"
text = path.read_text(encoding="utf-8").replace("\r\n", "\n")

text = exact_replace(
    text,
    "using Ryujinx.Graphics.GAL;",
    "using Ryujinx.Common.Logging;\nusing Ryujinx.Graphics.GAL;",
    "Ryujinx graphics using",
)

text = exact_replace(
    text,
    "using System.Runtime.InteropServices;",
    "using System.Runtime.InteropServices;\nusing System.Threading;",
    "System.Runtime.InteropServices using",
)

field_marker = "        protected Auto<DisposablePipeline> Pipeline;"
field_block = f"""        private static int _nextPipelineAbId;
        private static int _nextDescriptorAbId;
        private const int PipelineThrottleMilliseconds = {throttle_ms};

        private static bool ShouldLogPipelineAb(int id)
        {{
            return id <= 20 || id % 100 == 0;
        }}

{field_marker}"""
text = exact_replace(text, field_marker, field_block, "pipeline A-B field marker")

descriptor_call = "            _descriptorSetUpdater.UpdateAndBindDescriptorSets(Cbs, PipelineBindPoint.Graphics);"
descriptor_block = """            int descriptorAbId = Interlocked.Increment(ref _nextDescriptorAbId);
            bool logDescriptorAb = ShouldLogPipelineAb(descriptorAbId);

            if (logDescriptorAb)
            {
                Logger.Info?.Print(
                    LogClass.Gpu,
                    $"PipelineAB Descriptor G#{descriptorAbId}: begin.");
            }

            _descriptorSetUpdater.UpdateAndBindDescriptorSets(Cbs, PipelineBindPoint.Graphics);

            if (logDescriptorAb)
            {
                Logger.Info?.Print(
                    LogClass.Gpu,
                    $"PipelineAB Descriptor G#{descriptorAbId}: completed.");
            }"""
text = exact_replace(text, descriptor_call, descriptor_block, "graphics descriptor update call")

method_start = "        private bool CreatePipeline(PipelineBindPoint pbp)\n        {"
method_end = "\n        private unsafe void BeginRenderPass()"

if text.count(method_start) != 1:
    raise SystemExit(f"Expected exactly one CreatePipeline start, found {text.count(method_start)}.")

start = text.index(method_start)
end = text.index(method_end, start)

new_method = """        private bool CreatePipeline(PipelineBindPoint pbp)
        {
            // We can only create a pipeline if the have the shader stages set.
            if (_newState.Stages != null)
            {
                int pipelineAbId = Interlocked.Increment(ref _nextPipelineAbId);
                string pipelineKind = pbp == PipelineBindPoint.Compute ? "C" : "G";
                bool logPipelineAb = ShouldLogPipelineAb(pipelineAbId);

                if (logPipelineAb)
                {
                    Logger.Info?.Print(
                        LogClass.Gpu,
                        $"PipelineAB {pipelineKind}#{pipelineAbId}: enter throttleMs={PipelineThrottleMilliseconds}.");
                }

                if (pbp == PipelineBindPoint.Graphics && _renderPass == null)
                {
                    CreateRenderPass();
                }

                if (!_program.IsLinked)
                {
                    if (logPipelineAb)
                    {
                        Logger.Error?.Print(
                            LogClass.Gpu,
                            $"PipelineAB {pipelineKind}#{pipelineAbId}: program not linked.");
                    }

                    return false;
                }

                if (PipelineThrottleMilliseconds > 0)
                {
                    Thread.Sleep(PipelineThrottleMilliseconds);
                }

                if (logPipelineAb)
                {
                    Logger.Info?.Print(
                        LogClass.Gpu,
                        $"PipelineAB {pipelineKind}#{pipelineAbId}: native create begin.");
                }

                var pipeline = pbp == PipelineBindPoint.Compute
                    ? _newState.CreateComputePipeline(Gd, Device, _program, PipelineCache)
                    : _newState.CreateGraphicsPipeline(Gd, Device, _program, PipelineCache, _renderPass.Get(Cbs).Value);

                if (logPipelineAb)
                {
                    Logger.Info?.Print(
                        LogClass.Gpu,
                        $"PipelineAB {pipelineKind}#{pipelineAbId}: native create returned null={pipeline == null}.");
                }

                if (pipeline == null)
                {
                    return false;
                }

                ulong pipelineHandle = pipeline.GetUnsafe().Value.Handle;

                if (_currentPipelineHandle != pipelineHandle)
                {
                    _currentPipelineHandle = pipelineHandle;
                    Pipeline = pipeline;

                    PauseTransformFeedbackInternal();
                    Gd.Api.CmdBindPipeline(CommandBuffer, pbp, Pipeline.Get(Cbs).Value);

                    if (logPipelineAb)
                    {
                        Logger.Info?.Print(
                            LogClass.Gpu,
                            $"PipelineAB {pipelineKind}#{pipelineAbId}: bind completed.");
                    }
                }
            }

            return true;
        }
"""

text = text[:start] + new_method + text[end:]
path.write_text(text, encoding="utf-8")

#!/usr/bin/env python3

from pathlib import Path
import sys


def exact_replace(text: str, old: str, new: str, description: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Expected exactly one {description}, found {count}.")
    return text.replace(old, new, 1)


root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
path = root / "src/Ryujinx.Graphics.Vulkan/PipelineBase.cs"
text = path.read_text(encoding="utf-8").replace("\r\n", "\n")

text = exact_replace(
    text,
    "using Ryujinx.Graphics.GAL;",
    "using Ryujinx.Common.Logging;\nusing Ryujinx.Graphics.GAL;",
    "PipelineBase Ryujinx using block",
)

text = exact_replace(
    text,
    "using System;\nusing System.Collections.Generic;",
    "using System;\nusing System.Collections.Generic;\nusing System.Diagnostics;",
    "PipelineBase System using block",
)

text = exact_replace(
    text,
    "using System.Runtime.InteropServices;",
    "using System.Runtime.InteropServices;\nusing System.Threading;",
    "System.Runtime.InteropServices using",
)

field_marker = "        protected Auto<DisposablePipeline> Pipeline;"
field_diagnostics = """        private static int _nextPipelineDiagnosticId;
        private static int _nextDescriptorDiagnosticId;

        [DllImport(\"__Internal\", EntryPoint = \"os_proc_available_memory\")]
        private static extern UIntPtr OsProcAvailableMemory();

        private static ulong TryGetAvailableMemory()
        {
            try
            {
                return OsProcAvailableMemory().ToUInt64();
            }
            catch
            {
                return 0;
            }
        }

        private static long TryGetWorkingSet()
        {
            try
            {
                return Process.GetCurrentProcess().WorkingSet64;
            }
            catch
            {
                return -1;
            }
        }

        private static void LogMemoryProbe(string marker)
        {
            long workingSet = TryGetWorkingSet();
            long managed = GC.GetTotalMemory(false);
            ulong available = TryGetAvailableMemory();

            Logger.Info?.Print(
                LogClass.Gpu,
                $\"MemoryProbe {marker}: workingSet={workingSet}, managed={managed}, available={available}.\");
        }

"""
text = exact_replace(
    text,
    field_marker,
    field_diagnostics + field_marker,
    "diagnostic field insertion point",
)

descriptor_call = "            _descriptorSetUpdater.UpdateAndBindDescriptorSets(Cbs, PipelineBindPoint.Graphics);"
descriptor_probe = """            int descriptorDiagnosticId = Interlocked.Increment(ref _nextDescriptorDiagnosticId);
            Logger.Info?.Print(
                LogClass.Gpu,
                $\"DescriptorProbe G#{descriptorDiagnosticId}: update-and-bind begin.\");
            LogMemoryProbe($\"DescriptorProbe G#{descriptorDiagnosticId} before-update\");

            _descriptorSetUpdater.UpdateAndBindDescriptorSets(Cbs, PipelineBindPoint.Graphics);

            Logger.Info?.Print(
                LogClass.Gpu,
                $\"DescriptorProbe G#{descriptorDiagnosticId}: update-and-bind completed.\");
            LogMemoryProbe($\"DescriptorProbe G#{descriptorDiagnosticId} after-update\");"""
text = exact_replace(
    text,
    descriptor_call,
    descriptor_probe,
    "graphics descriptor update call",
)

method_start_marker = "        private bool CreatePipeline(PipelineBindPoint pbp)\n        {"
method_end_marker = "\n        private unsafe void BeginRenderPass()"

start_count = text.count(method_start_marker)
if start_count != 1:
    raise SystemExit(f"Expected exactly one CreatePipeline start marker, found {start_count}.")

start = text.index(method_start_marker)
end = text.index(method_end_marker, start)

create_pipeline_method = """        private bool CreatePipeline(PipelineBindPoint pbp)
        {
            // We can only create a pipeline if the have the shader stages set.
            if (_newState.Stages != null)
            {
                int pipelineDiagnosticId = Interlocked.Increment(ref _nextPipelineDiagnosticId);
                string pipelineKind = pbp == PipelineBindPoint.Compute ? \"C\" : \"G\";

                Logger.Info?.Print(
                    LogClass.Gpu,
                    $\"PipelineProbe {pipelineKind}#{pipelineDiagnosticId}: enter.\");
                LogMemoryProbe($\"PipelineProbe {pipelineKind}#{pipelineDiagnosticId} enter\");

                if (pbp == PipelineBindPoint.Graphics && _renderPass == null)
                {
                    Logger.Info?.Print(
                        LogClass.Gpu,
                        $\"PipelineProbe G#{pipelineDiagnosticId}: CreateRenderPass begin.\");
                    LogMemoryProbe($\"PipelineProbe G#{pipelineDiagnosticId} before-render-pass\");

                    CreateRenderPass();

                    Logger.Info?.Print(
                        LogClass.Gpu,
                        $\"PipelineProbe G#{pipelineDiagnosticId}: CreateRenderPass completed.\");
                    LogMemoryProbe($\"PipelineProbe G#{pipelineDiagnosticId} after-render-pass\");
                }

                if (!_program.IsLinked)
                {
                    Logger.Error?.Print(
                        LogClass.Gpu,
                        $\"PipelineProbe {pipelineKind}#{pipelineDiagnosticId}: program not linked.\");

                    return false;
                }

                Logger.Info?.Print(
                    LogClass.Gpu,
                    $\"PipelineProbe {pipelineKind}#{pipelineDiagnosticId}: native create begin.\");
                LogMemoryProbe($\"PipelineProbe {pipelineKind}#{pipelineDiagnosticId} before-native-create\");

                var pipeline = pbp == PipelineBindPoint.Compute
                    ? _newState.CreateComputePipeline(Gd, Device, _program, PipelineCache)
                    : _newState.CreateGraphicsPipeline(Gd, Device, _program, PipelineCache, _renderPass.Get(Cbs).Value);

                Logger.Info?.Print(
                    LogClass.Gpu,
                    $\"PipelineProbe {pipelineKind}#{pipelineDiagnosticId}: native create returned, null={pipeline == null}.\");
                LogMemoryProbe($\"PipelineProbe {pipelineKind}#{pipelineDiagnosticId} after-native-create\");

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

                    Logger.Info?.Print(
                        LogClass.Gpu,
                        $\"PipelineProbe {pipelineKind}#{pipelineDiagnosticId}: CmdBindPipeline begin.\");
                    LogMemoryProbe($\"PipelineProbe {pipelineKind}#{pipelineDiagnosticId} before-bind\");

                    Gd.Api.CmdBindPipeline(CommandBuffer, pbp, Pipeline.Get(Cbs).Value);

                    Logger.Info?.Print(
                        LogClass.Gpu,
                        $\"PipelineProbe {pipelineKind}#{pipelineDiagnosticId}: CmdBindPipeline completed.\");
                    LogMemoryProbe($\"PipelineProbe {pipelineKind}#{pipelineDiagnosticId} after-bind\");
                }
            }

            return true;
        }
"""

text = text[:start] + create_pipeline_method + text[end:]
path.write_text(text, encoding="utf-8")

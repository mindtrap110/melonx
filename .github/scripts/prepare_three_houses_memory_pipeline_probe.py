#!/usr/bin/env python3

from pathlib import Path
import sys
import textwrap


def exact_replace(text: str, old: str, new: str, description: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Expected exactly one {description}, found {count}.")
    return text.replace(old, new, 1)


def block(value: str) -> str:
    return textwrap.dedent(value).lstrip("\n")


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

field_old = block(
    """
        private ulong _currentPipelineHandle;

        protected Auto<DisposablePipeline> Pipeline;
    """
)

field_new = block(
    """
        private ulong _currentPipelineHandle;

        private static int _nextPipelineDiagnosticId;
        private static int _nextDescriptorDiagnosticId;

        [DllImport("__Internal", EntryPoint = "os_proc_available_memory")]
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
                $"MemoryProbe {marker}: workingSet={workingSet}, managed={managed}, available={available}.");
        }

        protected Auto<DisposablePipeline> Pipeline;
    """
)

text = exact_replace(text, field_old, field_new, "diagnostic field insertion point")

descriptor_old = block(
    """
            _descriptorSetUpdater.UpdateAndBindDescriptorSets(Cbs, PipelineBindPoint.Graphics);

            return true;
    """
)

descriptor_new = block(
    """
            int descriptorDiagnosticId = Interlocked.Increment(ref _nextDescriptorDiagnosticId);
            Logger.Info?.Print(
                LogClass.Gpu,
                $"DescriptorProbe G#{descriptorDiagnosticId}: update-and-bind begin.");
            LogMemoryProbe($"DescriptorProbe G#{descriptorDiagnosticId} before-update");

            _descriptorSetUpdater.UpdateAndBindDescriptorSets(Cbs, PipelineBindPoint.Graphics);

            Logger.Info?.Print(
                LogClass.Gpu,
                $"DescriptorProbe G#{descriptorDiagnosticId}: update-and-bind completed.");
            LogMemoryProbe($"DescriptorProbe G#{descriptorDiagnosticId} after-update");

            return true;
    """
)

text = exact_replace(text, descriptor_old, descriptor_new, "graphics descriptor update block")

create_old = block(
    """
        private bool CreatePipeline(PipelineBindPoint pbp)
        {
            // We can only create a pipeline if the have the shader stages set.
            if (_newState.Stages != null)
            {
                if (pbp == PipelineBindPoint.Graphics && _renderPass == null)
                {
                    CreateRenderPass();
                }

                if (!_program.IsLinked)
                {
                    // Background compile failed, we likely can't create the pipeline because the shader is broken
                    // or the driver failed to compile it.

                    return false;
                }

                var pipeline = pbp == PipelineBindPoint.Compute
                    ? _newState.CreateComputePipeline(Gd, Device, _program, PipelineCache)
                    : _newState.CreateGraphicsPipeline(Gd, Device, _program, PipelineCache, _renderPass.Get(Cbs).Value);

                if (pipeline == null)
                {
                    // Host failed to create the pipeline, likely due to driver bugs.

                    return false;
                }

                ulong pipelineHandle = pipeline.GetUnsafe().Value.Handle;

                if (_currentPipelineHandle != pipelineHandle)
                {
                    _currentPipelineHandle = pipelineHandle;
                    Pipeline = pipeline;

                    PauseTransformFeedbackInternal();
                    Gd.Api.CmdBindPipeline(CommandBuffer, pbp, Pipeline.Get(Cbs).Value);
                }
            }

            return true;
        }
    """
)

create_new = block(
    """
        private bool CreatePipeline(PipelineBindPoint pbp)
        {
            // We can only create a pipeline if the have the shader stages set.
            if (_newState.Stages != null)
            {
                int pipelineDiagnosticId = Interlocked.Increment(ref _nextPipelineDiagnosticId);
                string pipelineKind = pbp == PipelineBindPoint.Compute ? "C" : "G";

                Logger.Info?.Print(
                    LogClass.Gpu,
                    $"PipelineProbe {pipelineKind}#{pipelineDiagnosticId}: enter.");
                LogMemoryProbe($"PipelineProbe {pipelineKind}#{pipelineDiagnosticId} enter");

                if (pbp == PipelineBindPoint.Graphics && _renderPass == null)
                {
                    Logger.Info?.Print(
                        LogClass.Gpu,
                        $"PipelineProbe G#{pipelineDiagnosticId}: CreateRenderPass begin.");
                    LogMemoryProbe($"PipelineProbe G#{pipelineDiagnosticId} before-render-pass");

                    CreateRenderPass();

                    Logger.Info?.Print(
                        LogClass.Gpu,
                        $"PipelineProbe G#{pipelineDiagnosticId}: CreateRenderPass completed.");
                    LogMemoryProbe($"PipelineProbe G#{pipelineDiagnosticId} after-render-pass");
                }

                if (!_program.IsLinked)
                {
                    Logger.Error?.Print(
                        LogClass.Gpu,
                        $"PipelineProbe {pipelineKind}#{pipelineDiagnosticId}: program not linked.");

                    return false;
                }

                Logger.Info?.Print(
                    LogClass.Gpu,
                    $"PipelineProbe {pipelineKind}#{pipelineDiagnosticId}: native create begin.");
                LogMemoryProbe($"PipelineProbe {pipelineKind}#{pipelineDiagnosticId} before-native-create");

                var pipeline = pbp == PipelineBindPoint.Compute
                    ? _newState.CreateComputePipeline(Gd, Device, _program, PipelineCache)
                    : _newState.CreateGraphicsPipeline(Gd, Device, _program, PipelineCache, _renderPass.Get(Cbs).Value);

                Logger.Info?.Print(
                    LogClass.Gpu,
                    $"PipelineProbe {pipelineKind}#{pipelineDiagnosticId}: native create returned, null={pipeline == null}.");
                LogMemoryProbe($"PipelineProbe {pipelineKind}#{pipelineDiagnosticId} after-native-create");

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
                        $"PipelineProbe {pipelineKind}#{pipelineDiagnosticId}: CmdBindPipeline begin.");
                    LogMemoryProbe($"PipelineProbe {pipelineKind}#{pipelineDiagnosticId} before-bind");

                    Gd.Api.CmdBindPipeline(CommandBuffer, pbp, Pipeline.Get(Cbs).Value);

                    Logger.Info?.Print(
                        LogClass.Gpu,
                        $"PipelineProbe {pipelineKind}#{pipelineDiagnosticId}: CmdBindPipeline completed.");
                    LogMemoryProbe($"PipelineProbe {pipelineKind}#{pipelineDiagnosticId} after-bind");
                }
            }

            return true;
        }
    """
)

text = exact_replace(text, create_old, create_new, "PipelineBase CreatePipeline method")
path.write_text(text, encoding="utf-8")

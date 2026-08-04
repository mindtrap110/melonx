#!/usr/bin/env python3

from pathlib import Path
import sys


def exact_replace(text: str, old: str, new: str, description: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Expected exactly one {description}, found {count}.")
    return text.replace(old, new, 1)


if len(sys.argv) != 2:
    raise SystemExit("Usage: prepare_three_houses_native_pipeline_throttle.py <source-root>")

root = Path(sys.argv[1])

# The previous throttle branch slept on every pipeline lookup, including cache hits.
# That starved the render thread. Remove that hot-path delay while retaining its
# sparse request diagnostics.
pipeline_base_path = root / "src/Ryujinx.Graphics.Vulkan/PipelineBase.cs"
pipeline_base = pipeline_base_path.read_text(encoding="utf-8").replace("\r\n", "\n")
pipeline_base = exact_replace(
    pipeline_base,
    "        private const int PipelineThrottleMilliseconds = 4;",
    "        private const int PipelineThrottleMilliseconds = 0;",
    "request-path throttle constant",
)
pipeline_base_path.write_text(pipeline_base, encoding="utf-8")

# Apply throttling only after a ShaderCollection pipeline-cache miss. This means
# ordinary draw calls that reuse an existing pipeline are no longer delayed.
pipeline_state_path = root / "src/Ryujinx.Graphics.Vulkan/PipelineState.cs"
pipeline_state = pipeline_state_path.read_text(encoding="utf-8").replace("\r\n", "\n")

pipeline_state = exact_replace(
    pipeline_state,
    "using Ryujinx.Common.Memory;",
    "using Ryujinx.Common.Logging;\nusing Ryujinx.Common.Memory;",
    "Ryujinx.Common.Memory using",
)

pipeline_state = exact_replace(
    pipeline_state,
    "using System.Numerics;",
    "using System.Numerics;\nusing System.Threading;",
    "System.Numerics using",
)

field_marker = "        private const int MaxDynamicStatesCount = 9;"
field_block = """        private const int MaxDynamicStatesCount = 9;

        private static int _nativePipelineCreateId;
        private const int NativePipelineThrottleMilliseconds = 4;

        private static void ThrottleNativePipelineCreation(string pipelineKind)
        {
            int id = Interlocked.Increment(ref _nativePipelineCreateId);

            if (id <= 20 || id % 100 == 0)
            {
                Logger.Info?.Print(
                    LogClass.Gpu,
                    $"NativePipeline {pipelineKind}#{id}: cache miss; delaying {NativePipelineThrottleMilliseconds} ms before native creation.");
            }

            if (NativePipelineThrottleMilliseconds > 0)
            {
                Thread.Sleep(NativePipelineThrottleMilliseconds);
            }
        }"""
pipeline_state = exact_replace(
    pipeline_state,
    field_marker,
    field_block,
    "PipelineState constants marker",
)

compute_cache_miss = """            if (program.TryGetComputePipeline(ref SpecializationData, out var pipeline))
            {
                return pipeline;
            }

            var pipelineCreateInfo = new ComputePipelineCreateInfo"""
compute_cache_miss_replacement = """            if (program.TryGetComputePipeline(ref SpecializationData, out var pipeline))
            {
                return pipeline;
            }

            ThrottleNativePipelineCreation("C");

            var pipelineCreateInfo = new ComputePipelineCreateInfo"""
pipeline_state = exact_replace(
    pipeline_state,
    compute_cache_miss,
    compute_cache_miss_replacement,
    "compute pipeline cache-miss block",
)

graphics_cache_miss = """            if (program.TryGetGraphicsPipeline(ref Internal, out var pipeline))
            {
                return pipeline;
            }

            Pipeline pipelineHandle = default;"""
graphics_cache_miss_replacement = """            if (program.TryGetGraphicsPipeline(ref Internal, out var pipeline))
            {
                return pipeline;
            }

            ThrottleNativePipelineCreation("G");

            Pipeline pipelineHandle = default;"""
pipeline_state = exact_replace(
    pipeline_state,
    graphics_cache_miss,
    graphics_cache_miss_replacement,
    "graphics pipeline cache-miss block",
)

pipeline_state_path.write_text(pipeline_state, encoding="utf-8")

# MoltenVK may internally maximize concurrent shader/pipeline compilation.
# Disable that behavior to reduce transient native/Metal memory peaks.
app_path = root / "src/MeloNX/MeloNX/App/UI/MeloNXApp.swift"
app = app_path.read_text(encoding="utf-8").replace("\r\n", "\n")
compression_line = '        EnvironmentVariable(string: "MVK_CONFIG_SHADER_COMPRESSION_ALGORITHM", value: "1"),'
compression_block = compression_line + '\n        EnvironmentVariable(string: "MVK_CONFIG_SHOULD_MAXIMIZE_CONCURRENT_COMPILATION", value: "0"),'
app = exact_replace(
    app,
    compression_line,
    compression_block,
    "MoltenVK shader compression environment variable",
)
app_path.write_text(app, encoding="utf-8")

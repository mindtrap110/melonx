#!/usr/bin/env python3

from pathlib import Path
import sys


def exact_replace(text: str, old: str, new: str, description: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Expected exactly one {description}, found {count}.")
    return text.replace(old, new, 1)


if len(sys.argv) != 4:
    raise SystemExit(
        "Usage: prepare_three_houses_balanced_pacing.py "
        "<source-root> <pipeline-delay-ms> <command-pooling-on|command-pooling-off>"
    )

root = Path(sys.argv[1])
delay_ms = int(sys.argv[2])
pooling_mode = sys.argv[3]

if delay_ms not in {2, 3}:
    raise SystemExit(f"Unsupported pipeline delay: {delay_ms}")
if pooling_mode not in {"command-pooling-on", "command-pooling-off"}:
    raise SystemExit(f"Unsupported pooling mode: {pooling_mode}")

# Native-cache-only throttling did not pace the high-frequency cached pipeline
# request/descriptor path. Apply a smaller delay to every pipeline state request.
pipeline_path = root / "src/Ryujinx.Graphics.Vulkan/PipelineBase.cs"
pipeline = pipeline_path.read_text(encoding="utf-8").replace("\r\n", "\n")
pipeline = exact_replace(
    pipeline,
    "        private const int PipelineThrottleMilliseconds = 0;",
    f"        private const int PipelineThrottleMilliseconds = {delay_ms};",
    "pipeline request throttle constant",
)
pipeline_path.write_text(pipeline, encoding="utf-8")

# With prefill mode 2, MoltenVK needs one Metal command buffer per active
# Vulkan command buffer. Four active buffers provide earlier backpressure than
# the previous value of sixteen while still allowing multiple frames in flight.
app_path = root / "src/MeloNX/MeloNX/App/UI/MeloNXApp.swift"
app = app_path.read_text(encoding="utf-8").replace("\r\n", "\n")
app = exact_replace(
    app,
    'EnvironmentVariable(string: "MVK_CONFIG_MAX_ACTIVE_METAL_COMMAND_BUFFERS_PER_QUEUE", value: "16")',
    'EnvironmentVariable(string: "MVK_CONFIG_MAX_ACTIVE_METAL_COMMAND_BUFFERS_PER_QUEUE", value: "4")',
    "MoltenVK active command buffer limit",
)

if pooling_mode == "command-pooling-off":
    sync_line = '        EnvironmentVariable(string: "MVK_CONFIG_SYNCHRONOUS_QUEUE_SUBMITS", value: "1"),'
    pooling_block = sync_line + '\n        EnvironmentVariable(string: "MVK_CONFIG_USE_COMMAND_POOLING", value: "0"),'
    app = exact_replace(
        app,
        sync_line,
        pooling_block,
        "MoltenVK synchronous queue submit setting",
    )

app_path.write_text(app, encoding="utf-8")

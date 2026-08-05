#!/usr/bin/env python3

from pathlib import Path
import sys


def replace_once(text: str, old: str, new: str, description: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Expected exactly one {description}, found {count}.")
    return text.replace(old, new, 1)


if len(sys.argv) != 3:
    raise SystemExit(
        "Usage: prepare_three_houses_cbpool4.py "
        "<source-root> <mvk-pooling-on|mvk-pooling-off>"
    )

root = Path(sys.argv[1])
pooling_mode = sys.argv[2]

if pooling_mode not in {"mvk-pooling-on", "mvk-pooling-off"}:
    raise SystemExit(f"Unsupported pooling mode: {pooling_mode}")

# Ryujinx retains every resource referenced by an in-flight command buffer until
# that buffer's fence is recycled. On iOS, keeping sixteen primary command
# buffers in flight can retain far more shared Metal memory than MoltenVK's
# configured four-buffer limit suggests. Match the Ryujinx-side pool to four so
# fences are waited and dependent resources are released earlier.
cb_path = root / "src/Ryujinx.Graphics.Vulkan/CommandBufferPool.cs"
cb = cb_path.read_text(encoding="utf-8").replace("\r\n", "\n")
cb = replace_once(
    cb,
    "        public const int MaxCommandBuffers = 16;",
    "        public const int MaxCommandBuffers = 4;",
    "command-buffer pool size",
)
if "Flags = CommandBufferUsageFlags.OneTimeSubmitBit," not in cb:
    raise SystemExit("OneTimeSubmitBit patch is missing from the source branch.")
cb_path.write_text(cb, encoding="utf-8")

app_path = root / "src/MeloNX/MeloNX/App/UI/MeloNXApp.swift"
app = app_path.read_text(encoding="utf-8").replace("\r\n", "\n")

if pooling_mode == "mvk-pooling-off":
    pooling_line = '        EnvironmentVariable(string: "MVK_CONFIG_USE_COMMAND_POOLING", value: "0"),'
    if pooling_line not in app:
        anchor = '        EnvironmentVariable(string: "MVK_CONFIG_SYNCHRONOUS_QUEUE_SUBMITS", value: "1"),'
        app = replace_once(
            app,
            anchor,
            anchor + "\n" + pooling_line,
            "synchronous queue-submit setting",
        )
else:
    app = app.replace(
        '        EnvironmentVariable(string: "MVK_CONFIG_USE_COMMAND_POOLING", value: "0"),\n',
        "",
    )

app_path.write_text(app, encoding="utf-8")

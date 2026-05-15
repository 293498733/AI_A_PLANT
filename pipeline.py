#!/usr/bin/env python3
"""AI Dev Flow CLI 入口。

实际执行内核位于 pipeline.runner，供 CLI 与未来 Multica 适配器共同调用。
"""

from pipeline.runner import (  # noqa: F401
    PipelineRunner,
    build_arg_parser,
    main,
    request_from_args,
    setup_project,
    expand_params,
    banner,
    _prepare_requirement_input,
    _collect_requirement_interactively,
    _read_requirement_from_stdin,
    _will_run_stage,
    _file_fingerprint,
    _output_refreshed,
    _check_prerequisite,
)


if __name__ == "__main__":
    raise SystemExit(main())

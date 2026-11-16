#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from .sink_base import SinkAnalyzer


class CommandExecAnalyzer(SinkAnalyzer):
    vulnclass = "command-exec"
    catalog = "command_exec.yaml"

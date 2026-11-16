#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from .sink_base import SinkAnalyzer


class XssAnalyzer(SinkAnalyzer):
    vulnclass = "xss"
    catalog = "xss.yaml"

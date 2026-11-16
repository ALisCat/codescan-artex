#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from .sink_base import SinkAnalyzer


class SsrfAnalyzer(SinkAnalyzer):
    vulnclass = "ssrf"
    catalog = "ssrf.yaml"

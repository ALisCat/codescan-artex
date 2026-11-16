#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from .sink_base import SinkAnalyzer


class DeserializationAnalyzer(SinkAnalyzer):
    vulnclass = "deserialization"
    catalog = "deserialization.yaml"

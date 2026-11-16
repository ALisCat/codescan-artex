#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from .sink_base import SinkAnalyzer


class PathTraversalAnalyzer(SinkAnalyzer):
    vulnclass = "path-traversal"
    catalog = "path_traversal.yaml"

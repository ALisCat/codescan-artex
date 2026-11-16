#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from .sink_base import SinkAnalyzer


class FileUploadAnalyzer(SinkAnalyzer):
    vulnclass = "file-upload"
    catalog = "file_upload.yaml"

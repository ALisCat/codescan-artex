#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""XXE：XML 解析器是否关闭外部实体。"""
import re

from .base import Analyzer, Finding, POSSIBLE, IMPOSSIBLE
from .patterns import scan, has_input, model, search_policy

PARSER = [
    re.compile(r"(?i)(DocumentBuilderFactory|SAXParserFactory|XMLInputFactory|SAXReader|Unmarshaller|XPathFactory|XmlMapper|TransformerFactory)"),
]
HARDEN = [
    re.compile(r"(?i)(disallow-doctype-decl|external-general-entities|external-parameter-entities|ACCESS_EXTERNAL_DTD|ACCESS_EXTERNAL_SCHEMA|FEATURE_SECURE_PROCESSING|setExpandEntityReferences\s*\(\s*false)"),
]


class XxeAnalyzer(Analyzer):
    vulnclass = "xxe"

    def analyze(self, endpoint, ctx):
        parsers = scan(ctx, endpoint, PARSER, "xml_parser")
        if not parsers:
            return [Finding.make(endpoint, self.vulnclass, IMPOSSIBLE, {
                "scope": "endpoint", "subtype": "no-xml-parser",
            }, [], "no XML parser in flow")]
        if not has_input(endpoint):
            return [Finding.make(endpoint, self.vulnclass, IMPOSSIBLE, {
                "scope": "endpoint", "subtype": "no-request-input",
            }, [], "no request input")]
        guards = scan(ctx, endpoint, HARDEN, "xxe_hardening")
        gaps = [] if guards else ["external_entities_not_disabled"]
        m = model(["external_entities_disabled"], parsers + guards, gaps, extra={
            "parsers": parsers[:10],
            "search_policy": search_policy(gaps, ["disallow-doctype-decl|external-general-entities|ACCESS_EXTERNAL_DTD"]),
        })
        ev = {
            "xxe_model": m, "scope": "endpoint",
            "subtype": "xxe-unhardened" if gaps else "xxe-hardened",
            "cwe": ["CWE-611"], "tags": ["xxe"],
            "sites": parsers[:10],
        }
        return [Finding.make(endpoint, self.vulnclass, POSSIBLE, ev, [], gaps[0] if gaps else None)]

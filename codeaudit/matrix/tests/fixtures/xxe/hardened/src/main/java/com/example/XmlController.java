package com.example;

import java.io.StringReader;
import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import org.springframework.web.bind.annotation.*;
import org.xml.sax.InputSource;

@RestController
@RequestMapping("/api/xml")
public class XmlController {
    @PostMapping("/parse")
    public String parse(@RequestBody String xml) throws Exception {
        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
        factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
        factory.setFeature("http://xml.org/sax/features/external-general-entities", false);
        DocumentBuilder builder = factory.newDocumentBuilder();
        builder.parse(new InputSource(new StringReader(xml)));
        return "ok";
    }
}

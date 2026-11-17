package com.example;

import java.io.ByteArrayInputStream;
import java.io.ObjectInputStream;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/deserialize")
public class DeserializeController {
    @PostMapping("/object")
    public Object object(@RequestBody byte[] data) throws Exception {
        return new ObjectInputStream(new ByteArrayInputStream(data)).readObject();
    }
}

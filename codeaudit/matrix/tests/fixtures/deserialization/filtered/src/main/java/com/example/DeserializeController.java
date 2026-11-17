package com.example;

import java.io.ByteArrayInputStream;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/deserialize")
public class DeserializeController {
    @PostMapping("/object")
    public Object object(@RequestBody byte[] data) throws Exception {
        ObjectInputFilter filter = ObjectInputFilter.Config.createFilter("com.example.*;!*");
        ObjectInputStream in = new ObjectInputStream(new ByteArrayInputStream(data));
        in.setObjectInputFilter(filter);
        return in.readObject();
    }
}

package com.example;
import java.security.MessageDigest;
public class Crypto {
    public byte[] checksum(byte[] body) throws Exception {
        return MessageDigest.getInstance("MD5").digest(body);
    }
}

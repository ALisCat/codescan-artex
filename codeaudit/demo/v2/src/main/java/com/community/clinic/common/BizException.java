package com.community.clinic.common;

/**
 * 业务异常，统一由 GlobalExceptionHandler 转成 {"code":..,"msg":..,"data":null}
 */
public class BizException extends RuntimeException {

    private final int code;

    public BizException(String message) {
        this(500, message);
    }

    public BizException(int code, String message) {
        super(message);
        this.code = code;
    }

    public int getCode() {
        return code;
    }
}

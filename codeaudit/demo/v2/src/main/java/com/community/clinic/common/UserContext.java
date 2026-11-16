package com.community.clinic.common;

/**
 * 当前请求的登录用户（由 AuthInterceptor 写入，请求结束时清理）。
 */
public class UserContext {

    private static final ThreadLocal<LoginUser> HOLDER = new ThreadLocal<>();

    private UserContext() {
    }

    public static void set(LoginUser user) {
        HOLDER.set(user);
    }

    public static LoginUser get() {
        return HOLDER.get();
    }

    public static LoginUser require() {
        LoginUser user = HOLDER.get();
        if (user == null) {
            throw new BizException(401, "未登录");
        }
        return user;
    }

    public static void clear() {
        HOLDER.remove();
    }
}

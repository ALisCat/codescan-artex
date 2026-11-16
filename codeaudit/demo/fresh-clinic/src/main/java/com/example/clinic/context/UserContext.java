package com.example.clinic.context;

import com.example.clinic.model.ClinicModels.LoginUser;

public final class UserContext {

    private static final ThreadLocal<LoginUser> CURRENT_USER = new ThreadLocal<LoginUser>();

    private UserContext() {
    }

    public static void set(LoginUser user) {
        CURRENT_USER.set(user);
    }

    public static LoginUser get() {
        return CURRENT_USER.get();
    }

    public static void clear() {
        CURRENT_USER.remove();
    }
}

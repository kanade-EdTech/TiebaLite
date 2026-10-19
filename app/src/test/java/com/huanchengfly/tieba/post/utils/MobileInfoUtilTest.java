package com.huanchengfly.tieba.post.utils;

import org.junit.Test;

import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.Assert.assertEquals;

public class MobileInfoUtilTest {
    @Test
    public void doesNotReadHardwareOnAndroid10OrLater() {
        for (int api : new int[]{29, 30, 33, 36}) {
            for (boolean granted : new boolean[]{false, true}) {
                assertEquals(MobileInfoUtil.DEFAULT_IMEI,
                        MobileInfoUtil.readLegacyDeviceId(api, granted, () -> {
                            throw new AssertionError("Modern Android must not read device IDs");
                        }));
            }
        }
    }

    @Test
    public void doesNotReadWithoutPhonePermission() {
        for (int api : new int[]{21, 22, 23, 28}) {
            assertEquals(MobileInfoUtil.DEFAULT_IMEI,
                    MobileInfoUtil.readLegacyDeviceId(api, false, () -> {
                        throw new AssertionError("Unpermitted reads must not reach telephony");
                    }));
        }
    }

    @Test
    public void preservesLegacyIdentifierWhenAuthorized() {
        for (int api : new int[]{21, 22, 23, 28}) {
            AtomicInteger reads = new AtomicInteger();
            assertEquals("synthetic-device-id", MobileInfoUtil.readLegacyDeviceId(api, true, () -> {
                reads.incrementAndGet();
                return "synthetic-device-id";
            }));
            assertEquals(1, reads.get());
        }
    }

    @Test
    public void fallsBackWhenHardwareIdentifierIsUnavailable() {
        assertEquals(MobileInfoUtil.DEFAULT_IMEI,
                MobileInfoUtil.readLegacyDeviceId(28, true, () -> null));
    }

    @Test
    public void fallsBackWhenPhonePermissionIsRevoked() {
        assertEquals(MobileInfoUtil.DEFAULT_IMEI,
                MobileInfoUtil.readLegacyDeviceId(28, true, () -> {
                    throw new SecurityException("Permission revoked during read");
                }));
    }

    @Test
    public void fallsBackWhenTelephonyServiceFails() {
        assertEquals(MobileInfoUtil.DEFAULT_IMEI,
                MobileInfoUtil.readLegacyDeviceId(28, true, () -> {
                    throw new IllegalStateException("Telephony unavailable");
                }));
    }
}
